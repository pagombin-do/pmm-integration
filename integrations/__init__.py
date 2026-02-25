from .postgresql import PostgreSQLIntegration
from .mysql import MySQLIntegration
from .mongodb import MongoDBIntegration

ENGINE_MAP = {
    "pg": PostgreSQLIntegration,
    "postgresql": PostgreSQLIntegration,
    "mysql": MySQLIntegration,
    "mongodb": MongoDBIntegration,
}
