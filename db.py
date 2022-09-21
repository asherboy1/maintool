import pymysql

class ConnectMySQL:
    def __init__(self, db) -> None:
        try:
            self.conn = pymysql.connect(host=db['host'], port=int(db['port']), user=db['user'], password=db['password'], database=db['database'])
        except KeyError:
            raise ValueError("检查数据库配置")
        self.cursor = self.conn.cursor(pymysql.cursors.DictCursor)

    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cursor.close()
        self.conn.close()