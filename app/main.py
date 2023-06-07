from fastapi import FastAPI, Query, HTTPException
from fastapi.encoders import jsonable_encoder
from typing import List
import pandas as pd
from pmdarima.arima import auto_arima
from prophet import Prophet
import uvicorn
from sklearn.metrics import mean_squared_error
import numpy as np


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

    # Validar o JSON recebido pela API e ajustar o dataframe
    df, time_series = verify_input(df)

    # Dividir a série temporal em treino e teste
    train_size = int(len(time_series) * 0.8) 
    train, test = time_series[:train_size], time_series[train_size:]

    # Criar os modelos
    arima_model = create_arima_model(train)  
    prophet_model = create_prophet_model(train)

    # Fazer a previsão para os meses de treino
    arima_forecast = arima_predict(arima_model, len(df) - train_size)
    prophet_forecast = prophet_predict(prophet_model, len(df) - train_size)

    # Calcular RMSE
    arima_rmse = np.sqrt(mean_squared_error(test, arima_forecast))
    prophet_rmse = np.sqrt(mean_squared_error(test, prophet_forecast))

    # Comparar os RMSE obtidos
    if arima_rmse < prophet_rmse:
        arima_model = create_arima_model(df['quantidade'])  
        forecast = arima_predict(arima_model, meses)
        model_name = "ARIMA"
    else:
        prophet_model = create_prophet_model(df)
        prophet_forecast = prophet_predict(prophet_model, meses)
        forecast = prophet_forecast['yhat'][-meses:]
        model_name = "Prophet"

    response_api = prepare_response(forecast, df, decimal, train, test, arima_rmse, prophet_rmse, model_name)

    return response_api


# Iniciar o servidor da API
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)


# Função para validar os dados recebidos pela API e ajustar o dataframe
def verify_input(df):
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
    
    # Converter a coluna 'mês' para o formato de data
    df['mes'] = pd.to_datetime(df['mes'])

    # Verificar se algum gap de data na coluna 'mes'
    data_range = pd.date_range(start=df['mes'].min(), end=df['mes'].max(), freq='MS')
    missing_months = data_range[~data_range.isin(df['mes'])]
    if not missing_months.empty:
        raise HTTPException(status_code=400, detail="Existem meses sem informação: " + ", ".join(map(str, missing_months.strftime("%Y-%m"))))
    
    # Ordenar o DataFrame pela coluna de mês
    df.sort_values('mes', inplace=True)

    # Criar uma série temporal com o índice sendo a coluna 'mês'
    time_series = pd.Series(df['quantidade'].values, index=df['mes'])

    return df, time_series

    
# Modelo ARIMA 
def create_arima_model(dataframe):
    # Verifica se a série temporal informada é maior de 12 meses para realizar análise sazonal
    if len(dataframe.index.unique()) >= 12:
        arima_model = auto_arima(dataframe, start_p=1, start_q=1, max_p=6, max_q=6, start_P=0, seasonal=True, d=1, D=1, trace=False, error_action='ignore', suppress_warnings=True, stepwise=False)
    else:
        arima_model = auto_arima(dataframe, start_p=1, start_q=1, max_p=6, max_q=6, start_P=0, trace=False, error_action='ignore', suppress_warnings=True, stepwise=False)

    return arima_model


# Modelo Prophet
def create_prophet_model(dataframe):
    prophet_model = Prophet()

    # Adequar o dataframe para o padrão exigido pelo Prophet
    prophet_df = pd.DataFrame({'ds': dataframe.index, 'y': dataframe.values})
    prophet_model.fit(prophet_df)

    return prophet_model


# Realizar a predição pelo modelo ARIMA
def arima_predict(arima_model, periodos):
    arima_forecast = arima_model.predict(n_periods=periodos)

    return arima_forecast


# Realizar a predição pelo modelo Prophet
def prophet_predict(prophet_model, periodos):
    future_dates = prophet_model.make_future_dataframe(periods=periodos)
    prophet_forecast = prophet_model.predict(future_dates)['yhat'].tail(periodos)

    return prophet_forecast


# Função para formatar a resposta da API
def prepare_response(forecast, df, decimal, train, test, arima_rmse, prophet_rmse, model_name):
    # Converter o resultado para um dicionário com duas listas (meses e quantidades)
    previsoes = []
    for i in range(len(forecast)):
        date = pd.to_datetime(df['mes'].max()) + pd.DateOffset(months=i+1)
        previsao = {
            "mes": date.strftime("%Y-%m"),
            "quantidade": round(forecast.iloc[i], decimal)
        }
        previsoes.append(previsao)

    # Formatar o resultado em um JSON para retornar pela API
    result = {
        "estatistica": {
            "divisaoSerieTemporal": {
                "mesesTreinamento": int(len(train)),
                "mesesTeste": int(len(test))
            },
            "RMSE": {
                "ARIMA": arima_rmse.round(decimal),
                "Prophet": prophet_rmse.round(decimal)
            },
            "modeloSelecionado": model_name
        },
        "previsao": jsonable_encoder(previsoes)
        }
    
    return result