import atexit
import logging
from flask import Flask
from .config import db
from endpoints import stock_blueprint

app = Flask("stock-service")

# Register the Blueprint
app.register_blueprint(stock_blueprint, url_prefix="/api")


# Close the database connection on exit
def close_db_connection():
    db.close()


atexit.register(close_db_connection)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
else:
    gunicorn_logger = logging.getLogger("gunicorn.error")
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)
