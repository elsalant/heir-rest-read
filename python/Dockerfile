
FROM python:3.8-slim

WORKDIR /app
COPY restFHIR.py restFHIR.py
COPY requirements.txt requirements.txt
RUN apt-get update && apt-get install -y musl-dev python3-dev gcc
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir pyyaml
RUN pip install --no-cache-dir --upgrade pip && \
    pip install -r requirements.txt
#ENTRYPOINT ["python3"]
ENV PYTHONUNBUFFERED=1
CMD ["python3", "./restFHIR.py"]

