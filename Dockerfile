FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p data output/statements assets

EXPOSE 8050

CMD ["python3", "launch.py", "--data-dir", "data", "--port", "8050", "--no-browser"]
