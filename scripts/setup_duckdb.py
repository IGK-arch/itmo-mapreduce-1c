"""Install the official S3 extension before timed benchmark runs."""
import bootstrap
from vacancy_lab.duckdb_engine import connect

if __name__ == '__main__':
    con = connect(install=True)
    print(con.execute("SELECT extension_name, loaded FROM duckdb_extensions() WHERE extension_name='httpfs'").fetchall())
    con.close()
