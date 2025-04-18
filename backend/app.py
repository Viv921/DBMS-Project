from flask import Flask
from flask_cors import CORS
from dotenv import load_dotenv

import db
from api.schema_routes import schema_bp
from api.query_routes import query_bp
from api.dml_routes import dml_bp
from api.normalization_routes import normalization_bp

load_dotenv()
app = Flask(__name__)
CORS(app)

app.register_blueprint(schema_bp)
app.register_blueprint(query_bp)
app.register_blueprint(dml_bp)
app.register_blueprint(normalization_bp)

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True, port=5000)