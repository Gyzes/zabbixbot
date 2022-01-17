FROM python:3.9-alpine

WORKDIR /app
COPY requirements.txt requirements.txt
COPY send.py send.py

RUN set -ex \
 && pip install -r requirements.txt \
 && python --version \
 && pip --version 

CMD python -u send.py
