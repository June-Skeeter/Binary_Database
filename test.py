from database import database
import pandas as pd
import numpy as np

index = pd.date_range(
    '2024-09-01T00:00:00+00:00','2026-01-01T00:00:00+00:00',freq='30Min'
)

df = pd.DataFrame(
    index=index,
    data = {'j':[np.random.randint(len(index))]},
    # dtype = {'A':'float32'}
)
df['j'] = df['j'].astype('float32')
database(databasePath='testDatabase').loadFile(df)
df = database(databasePath='testDatabase').loadDatabase(startYear=2023,stopYear=2025)

print(df)
print(df.dtypes)