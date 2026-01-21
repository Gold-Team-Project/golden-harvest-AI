import pandas as pd

def render_excel(columns, rows, filename):
    df = pd.DataFrame(rows, columns=columns)
    df.to_excel(filename, index=False)
    return filename
