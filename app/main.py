from fastapi import FastAPI, Query, HTTPException
from fastapi.encoders import jsonable_encoder
from typing import List
import pandas as pd
from pmdarima.arima import auto_arima
import uvicorn

# Instanciar a API
app = FastAPI()

# Rota para verificar se a API está online
@app.get('/status')
def read_root():
    return {"statusApi": "online"}

# Rota para realizar a predição
@app.post("/predicao")
def predict(data: List[dict], meses: int = Query(..., gt=0), decimal: int = Query(0)):
    # Converter o JSON recebido em um DataFrame do Pandas
    df = pd.DataFrame(data)

    # Verificar se as colunas 'mes' e 'quantidade' estão presentes no DataFrame
    if 'mes' not in df.columns or 'quantidade' not in df.columns:
        raise HTTPException(status_code=400, detail= "As colunas 'mes' e 'quantidade' são obrigatórias.")

    # Verificar se as colunas 'mes' e 'quantidade' possuem valores não nulos
    if df['mes'].isnull().any() or df['quantidade'].isnull().any():
        raise HTTPException(status_code=400, detail= "As colunas 'mes' e 'quantidade' não podem conter valores nulos.")

    # Verificar se a coluna 'mes' possui datas no formato correto (YYYY-MM)
    pattern = r'^\d{4}-\d{2}$'
    valid_dates = df['mes'].str.match(pattern)

    # Verificar se todas as datas são válidas
    if not valid_dates.all():
        raise HTTPException(status_code=400, detail= "A coluna 'mes' possui data(s) inválida(s).")
    
    # Verificar se existem valores duplicados na coluna 'mes'
    duplicates = df['mes'].duplicated()

    # Verificar se há algum valor duplicado
    if duplicates.any():
        duplicated_values = df['mes'][duplicates].unique()
        raise HTTPException(status_code=400, detail=f"Valores duplicados encontrados: {', '.join(duplicated_values)}")

    # Converter a coluna de mês para o formato de data
    df['mes'] = pd.to_datetime(df['mes'])

    # Verificar se algum valor do intervalo de datas está ausente na coluna 'mes'
    data_range = pd.date_range(start=df['mes'].min(), end=df['mes'].max(), freq='MS')
    missing_months = data_range[~data_range.isin(df['mes'])]
    if not missing_months.empty:
        raise HTTPException(status_code=400, detail="Existem meses sem informação: " + ", ".join(map(str, missing_months.strftime("%Y-%m"))))

    # Ordenar o DataFrame pela coluna de mês
    df.sort_values('mes', inplace=True)

    # Criar uma série temporal com o índice sendo a coluna de mês e os valores sendo a quantidade mensal
    time_series = pd.Series(df['quantidade'].values, index=df['mes'])
     
    # Verifica se a série temporal informada é maior de 12 meses para realizar análise sazonal
    if len(time_series.index.unique()) >= 12:
        stepwise_model = auto_arima(time_series, start_p=1, start_q=1, max_p=6, max_q=6, start_P=0, seasonal=True, d=1, D=1, trace=False, error_action='ignore', suppress_warnings=True, stepwise=False)
    else:
        stepwise_model = auto_arima(time_series, start_p=1, start_q=1, max_p=6, max_q=6, start_P=0, trace=False, error_action='ignore', suppress_warnings=True, stepwise=False)
    
    # Fazer a previsão para os próximos três meses
    forecast = pd.DataFrame(stepwise_model.predict(n_periods=meses))

    # Converter o resultado para um dicionário com duas listas (meses e quantidades)
    previsoes = []
    for i in range(len(forecast)):

        if decimal < 1:
            qtd = int(forecast.iloc[i, 0].round(decimal))
        else:
            qtd = forecast.iloc[i, 0].round(decimal)

        previsao = {
            "mes": forecast.index[i].strftime("%Y-%m"),
            "quantidade": qtd
        }
        previsoes.append(previsao)

    # Formatar o resultado em um JSON para retornar pela API
    result = {"previsao": jsonable_encoder(previsoes)}

    return result

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)