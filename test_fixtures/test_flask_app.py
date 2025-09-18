from flask import Flask
from flask import jsonify
import pytest


app = Flask(__name__)


@app.route("/hello/<int:post_id>")
def hello(post_id):
    return jsonify({"id": post_id})


if __name__ == "__main__":
    app.run(debug=True)


@pytest.fixture()
def client():
    return app.test_client()


@pytest.fixture()
def runner(app):
    return app.test_cli_runner()


def test_request_one(client):
    response = client.get("/hello/42")
    assert b"42" in response.data
