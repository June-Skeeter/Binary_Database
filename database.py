from dataclasses import dataclass, field
from pandas.api.types import is_float_dtype,is_integer_dtype
import pandas as pd
import numpy as np
import os

@dataclass(kw_only=True)
class database:
    databasePath: str 
    databaseInterval: float = 1800.0
    # dtypeDefault: str = 'float32'
    # timestamp: str = 'posixtime.int64'
    intMask: str = -9999
    timezone: str = 'UTC'

    def __post_init__(self):
        if 'YYYY' not in self.databasePath:
            print(f'reformatting to {self.databasePath}/yyyy')
            self.databasePath = os.path.join(self.databasePath,'yyyy')
        self.timedelta = pd.to_timedelta(self.databaseInterval,unit='s')
        
    def loadFile(self,dataframe):
        # Assumes timestamp represents end of observation interval
        # Create timestamp
        ix = dataframe.index-self.timedelta
        ix = pd.date_range(f"{dataframe.index.year.min()}-01-01T00:00:00+00:00",f"{dataframe.index.year.max()}-01-01T00:00:00+00:00",freq=self.timedelta,inclusive='left')+self.timedelta
        timestamp = pd.Series(
            index = ix,
            name = 'posixtime',
            data = ((ix.astype(int)//1e6).values).astype('int64') if ix.unit=='us' else ((ix.astype(int)//1e9).values).astype('int64')
        )
        # Get dtypes and join timestamp
        dtypesIn = dataframe.dtypes
        integers = dtypesIn[[is_integer_dtype(d) for d in dtypesIn]].index
        dataOut = pd.DataFrame(timestamp).join(dataframe)
        # Fill int nans the recast types
        dataOut[integers] = dataOut[integers].fillna(self.intMask)
        dataOut = dataOut.astype(dtypesIn)
        # Get start of each year
        yix = pd.date_range(f"{ix.year.min()}-01-01T00:00:00+00:00",f"{ix.year.max()+1}-01-01T00:00:00+00:00",freq='YS',inclusive='left')+self.timedelta
        # Write each year to database

        for yyyy in yix:
            pth = self.databasePath.replace('yyyy',f"{yyyy.year}")
            print(pth)
            os.makedirs(pth,exist_ok=True)
            # write each column with dtype as file extension
            for colName,dtype in dataOut.dtypes.items():
                dataOut.loc[
                    ((dataOut.index>=yyyy)&(dataOut.index<yyyy+pd.DateOffset(years=1))),colName
                    ].values.tofile(os.path.join(pth,f"{colName}.{str(dtype)}"))

    def loadDatabase(self,startYear,stopYear):
        df = {}
        cols = []
        for yyyy in range(startYear,stopYear+1):
            pth = self.databasePath.replace('yyyy',f"{yyyy}")
            if not os.path.isdir(pth): exit(f"Warning:\n\nNot a database folder: {pth}")
            df[yyyy] = pd.DataFrame({(fn.split('.')[0],fn.rsplit('.')[-1]):np.fromfile(os.path.join(pth,fn),dtype = fn.rsplit('.')[-1]) for fn in os.listdir(pth)})
            cols = cols + list(df[yyyy].columns)
        cols = list(set(cols))
        for yyyy in range(startYear,stopYear+1):
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
        dataOut.index = pd.to_datetime(dataOut[('posixtime','int64')],unit='s')
        dataOut.index = dataOut.index.tz_localize(self.timezone)
        return (dataOut)
        

