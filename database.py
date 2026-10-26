from dataclasses import dataclass, field
from pandas.api.types import is_float_dtype,is_integer_dtype
import pandas as pd
import numpy as np
import json
import os

@dataclass(kw_only=True)
class database:
    databasePath: str 
    databaseInterval: float = 1800.0
    # dtypeDefault: str = 'float32'
    # timestamp: str = 'posixtime.int64'
    intMask: str = 9999
    timezone: str = 'UTC'
    errors: str = 'raise'
    metaFile: str = '_metadata.json'

    def __post_init__(self):
        if 'yyyy' not in self.databasePath:
            print(f'reformatting to {self.databasePath}/yyyy')
            self.databasePath = os.path.join(self.databasePath,'yyyy')
        self.timedelta = pd.to_timedelta(self.databaseInterval,unit='s')
        
    def loadDataFrame(self,dataframe):
        if dataframe.empty:
            return (False)
        elif dataframe.index.duplicated().sum():
            return (f"Warning: Duplicated timestamps in database submission: {dataframe.index[dataframe.index.duplicated(keep=False)].values}\n fix before proceeding")
        if dataframe.columns.names == [None] or len(dataframe.columns.names)==1:
            metadata = {col:{'variableName':col,'dataType':str(dataframe[col].dtype)} for col in dataframe.columns}
        else:
            metadata = {col[0]:{vn:col[i] for i,vn in enumerate(dataframe.columns.names)} for col in dataframe.columns}

        # set to uct if not already
        if dataframe.index.tz is None:
            dataframe.index = dataframe.index.tz_localize('UTC')
        else:
            dataframe.index = dataframe.index.tz_convert('UTC')
        
        dataframe.columns = list(metadata.keys())
        # Assumes timestamp represents end of observation interval
        # Create timestamp
        ix = dataframe.index-self.timedelta
        ix = pd.date_range(f"{dataframe.index.year.min()}-01-01T00:00:00+00:00",f"{dataframe.index.year.max()+1}-01-01T00:00:00+00:00",freq=self.timedelta,inclusive='left')+self.timedelta
        timestamp = pd.Series(
            index = ix,
            name = 'posixtime',
            data = ((ix.astype(int)//1e6).values).astype('int64') if ix.unit=='us' else ((ix.astype(int)//1e9).values).astype('int64')
        )
        # Get dtypes and join timestamp
        dtypesIn = dataframe.dtypes
        integers = dtypesIn[[is_integer_dtype(d) for d in dtypesIn]].index
        allDataOut = pd.DataFrame(timestamp).join(dataframe)
        # Fill int nans the recast types
        allDataOut[integers] = allDataOut[integers].fillna(self.intMask)
        allDataOut = allDataOut.astype(dtypesIn)
        # Get start of each year
        yix = pd.date_range(f"{ix.year.min()}-01-01T00:00:00+00:00",f"{ix.year.max()}-01-01T00:00:00+00:00",freq='YS',inclusive='left')+self.timedelta
        # Write each year to database

        for yyyy in yix:
            pth = self.databasePath.replace('yyyy',f"{yyyy.year}")
            dataOut = allDataOut.loc[((allDataOut.index>=yyyy)&(allDataOut.index<yyyy+pd.DateOffset(years=1)))].copy()
            if os.path.isdir(pth):
                dataIn,metadataIn = self.readFolder(pth)
                dataIn.columns = dataIn.columns.get_level_values(0)
                # Fill missing (this part only works for floats)
                dataOut = dataOut.fillna(dataIn)
                # repeat for integers
                ints = [i for i in integers if i in dataIn.columns]
                if len(ints)>0:
                    dataOut[ints] = dataOut[ints].replace({self.intMask:np.nan}).fillna(dataIn[ints]).astype(dataIn[ints].dtypes)
            else:
                os.makedirs(pth)
            # write each column with dtype as file extension
            for colName,dtype in dataOut.dtypes.items():
                if is_float_dtype(dtype) or is_integer_dtype(dtype):
                    dataOut[colName].values.tofile(os.path.join(pth,f"{colName}.{str(dtype)}"))
                else:
                    print(f'Ignoring non-numeric variable: {colName}')
                
            with open(os.path.join(pth,self.metaFile),'w+') as f:
                json.dump(metadata,f)
        return(True)

    def readFolder(self,pth):
        with open(os.path.join(pth,self.metaFile)) as f:
            metadataOut = json.load(f)
        exclude = ['.json','.yml','.txt','.csv','.gitignore','.ini','.py','.r']
        dataOut = pd.DataFrame({(fn.split('.')[0],fn.rsplit('.')[-1]):np.fromfile(os.path.join(pth,fn),dtype = fn.rsplit('.')[-1]) for fn in os.listdir(pth) if not any([fn.lower().endswith(ext) for ext in exclude])})
        dataOut.index = pd.to_datetime(dataOut[('posixtime','int64')],unit='s')
        dataOut.index = dataOut.index.tz_localize(self.timezone)
        return(dataOut,metadataOut)

    def loadDatabase(self,startYear,stopYear):
        df = {}
        md = {}
        cols = []
        for yyyy in range(startYear,stopYear+1):
            pth = self.databasePath.replace('yyyy',f"{yyyy}")
            if not os.path.isdir(pth): 
                if self.errors == 'raise':
                    exit(f"Warning:\n\nNot a database folder: {pth}")
                else:
                    df[yyyy] = pd.DataFrame()
            else:
                df[yyyy],md[yyyy] = self.readFolder(pth)
                cols = cols + list(df[yyyy].columns)
        cols = list(set(cols))
        for yyyy in range(startYear,stopYear+1):
            if df[yyyy].empty:
                continue
            missing = [c for c in cols if c not in df[yyyy].columns]
            if len(missing):
                # missingInt = missing[m[1] for m in missing]
                missingInt = [m for m in missing if is_integer_dtype(m[1])]
                missingData = pd.DataFrame(index=df[yyyy].index,columns=missing)
                missingData[missingInt] = missingData[missingInt].fillna(self.intMask)
                missingData = missingData.astype(pd.Series([m[1] for m in missing],index=missing))
                missingData.columns = pd.MultiIndex.from_tuples(missing)
                df[yyyy] = df[yyyy].join(missingData)
        dataOut = pd.concat([data for data in df.values()])
        metadataOut = {}
        for yyyy in md.keys():
            if metadataOut == {}:
                metadataOut = md[yyyy]
            else:
                if metadataOut != md[yyyy]:
                    for k,v in md[yyyy].items():
                        if k not in metadataOut:
                            metadataOut[k] = md[yyyy][k]
                        else:
                            exit(f'Warning: Metadata do not match for {k}:\n current {metadataOut[k]}, incoming {md[yyyy][k]}')
        metadataOut = {md[yyyy] for yyyy in md.keys()}
        return (dataOut)
        

