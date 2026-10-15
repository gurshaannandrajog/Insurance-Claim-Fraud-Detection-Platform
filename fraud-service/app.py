"""Run the fraud-detection service:  python app.py   (listens on FRAUD_SERVICE_PORT, default 5001)."""
import logging
import os

from fraud_service import create_app

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
app = create_app()

if __name__ == "__main__":
    app.run(host=os.environ.get("FRAUD_SERVICE_HOST", "127.0.0.1"),
            port=int(os.environ.get("FRAUD_SERVICE_PORT", "5001")), debug=False)
