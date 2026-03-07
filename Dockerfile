FROM freqtradeorg/freqtrade:stable

USER root
RUN pip install xgboost lightgbm torch transformers httpx
USER ftuser

WORKDIR /freqtrade

COPY user_data/ /freqtrade/user_data/
COPY .env /freqtrade/.env

CMD ["freqtrade", "trade", "--config", "user_data/config.json", "--strategy", "AICryptoStrategy"]
