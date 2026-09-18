from flask import Flask

app = Flask(__name__)

MESSAGE = "こんにちは"

@app.route('/')
def hello_world():
  return {"message": MESSAGE}
