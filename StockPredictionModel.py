import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from statsmodels.tsa.arima.model import ARIMA
from statsmodels.tsa.statespace.sarimax import SARIMAX

# Load data
#Here in df add your own data set.
#This model use ARIMA and SARIMA model.
df = pd.read_csv('timeseries-daily-stocks.csv')
symbol = 'A'  # adjust your symbol here
df_symbol = df[df['symbol'] == symbol].copy()
df_symbol['date'] = pd.to_datetime(df_symbol['date'])
df_symbol.set_index('date', inplace=True)
ts = df_symbol['close']

# Use last 40 points only
ts_last = ts[-1000:]

# ARIMA order params (adjust based on your ACF/PACF)
#This values changes according to data.
p, d, q = 1, 1, 0

# SARIMA seasonal order params (adjust as needed)
# This values change according to data.
P, D, Q, s = 1, 1, 1, 2

forecast_steps = 30

# ----- Fit ARIMA ----- #
arima_model = ARIMA(ts_last, order=(p, d, q))
arima_result = arima_model.fit()

# ----- Fit SARIMA ----- #
sarima_model = SARIMAX(ts_last, order=(p, d, q), seasonal_order=(P, D, Q, s))
sarima_result = sarima_model.fit(disp=False)

# Forecast index including last observed date for continuity
last_date = ts_last.index[-1]
sim_dates = pd.date_range(start=last_date, periods=forecast_steps + 1, freq='B')

# ----- Forecast ARIMA ----- #
arima_forecast = arima_result.get_forecast(steps=forecast_steps)
arima_mean = arima_forecast.predicted_mean
arima_ci = arima_forecast.conf_int(alpha=0.10)  # 90% conf interval

# ----- Forecast SARIMA ----- #
sarima_forecast = sarima_result.get_forecast(steps=forecast_steps)
sarima_mean = sarima_forecast.predicted_mean
sarima_ci = sarima_forecast.conf_int(alpha=0.10)  # 90% conf interval

# ----- Plot results ----- #

fig, axes = plt.subplots(2, 1, figsize=(14, 12), sharex=True)

# ARIMA plot
axes[0].plot(ts_last, label='Historical Data', marker='o')
axes[0].plot(sim_dates[1:], arima_mean, label='Forecast', color='blue')
axes[0].fill_between(sim_dates[1:], arima_ci.iloc[:, 0], arima_ci.iloc[:, 1], color='blue', alpha=0.2, label='90% Confidence Interval')

axes[0].set_title('ARIMA Forecast')
axes[0].set_ylabel('Close Price')
axes[0].set_ylim(bottom=ts_last.min() * 0.9, top=200)
axes[0].legend()

# SARIMA plot
axes[1].plot(ts_last, label='Historical Data', marker='o')
axes[1].plot(sim_dates[1:], sarima_mean, label='Forecast', color='green')
axes[1].fill_between(sim_dates[1:], sarima_ci.iloc[:, 0], sarima_ci.iloc[:, 1], color='green', alpha=0.2, label='90% Confidence Interval')

axes[1].set_title('SARIMA Forecast')
axes[1].set_xlabel('Date')
axes[1].set_ylabel('Close Price')
axes[1].set_ylim(bottom=ts_last.min() * 0.9, top=200)
axes[1].legend()

plt.tight_layout()
plt.show()

#Note :- This code is for stock price3 predection. It may be goes Wrong. Do it at your risk.
