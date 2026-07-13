"""数据库浏览器 — 连接远程数据库，浏览表/列/数据"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from app.deps import get_current_user

router = APIRouter(dependencies=[Depends(get_current_user)])


class DBConnectRequest(BaseModel):
    db_type: str = "mysql"  # mysql | postgres
    host: str = "localhost"
    port: int = 3306
    user: str = "root"
    password: str = ""
    database: str = ""


def _get_conn(req: DBConnectRequest):
    if req.db_type == "mysql":
        import pymysql
        return pymysql.connect(
            host=req.host, port=req.port, user=req.user,
            password=req.password, database=req.database,
            charset="utf8mb4", connect_timeout=5,
        )
    elif req.db_type == "postgres":
        import psycopg2
        return psycopg2.connect(
            host=req.host, port=req.port, user=req.user,
            password=req.password, dbname=req.database,
            connect_timeout=5,
        )
    else:
        raise HTTPException(400, f"不支持的数据库类型: {req.db_type}")


@router.post("/db/test-connection")
def test_connection(req: DBConnectRequest):
    """测试数据库连接是否成功"""
    try:
        conn = _get_conn(req)
        conn.close()
        return {"ok": True, "message": f"成功连接到 {req.db_type}://{req.host}:{req.port}/{req.database}"}
    except Exception as e:
        return {"ok": False, "message": f"连接失败: {str(e)}"}


@router.post("/db/tables")
def list_tables(req: DBConnectRequest):
    """列出数据库中所有表"""
    try:
        conn = _get_conn(req)
        cur = conn.cursor()
        if req.db_type == "mysql":
            cur.execute("SHOW TABLES")
            tables = [row[0] for row in cur.fetchall()]
        else:
            cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = %s", (req.database,))
            tables = [row[0] for row in cur.fetchall()]
        cur.close()
        conn.close()
        return {"tables": tables}
    except Exception as e:
        raise HTTPException(400, f"获取表列表失败: {str(e)}")


@router.post("/db/columns")
def list_columns(req: DBConnectRequest, table_name: str):
    """列出指定表的所有列及其类型"""
    try:
        conn = _get_conn(req)
        cur = conn.cursor()
        if req.db_type == "mysql":
            cur.execute(f"DESCRIBE `{table_name}`")
            columns = [{"name": row[0], "type": row[1]} for row in cur.fetchall()]
        else:
            cur.execute(
                "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = %s ORDER BY ordinal_position",
                (table_name,),
            )
            columns = [{"name": row[0], "type": row[1]} for row in cur.fetchall()]
        cur.close()
        conn.close()
        return {"table": table_name, "columns": columns}
    except Exception as e:
        raise HTTPException(400, f"获取列信息失败: {str(e)}")


@router.post("/db/preview")
def preview_data(req: DBConnectRequest, table_name: str, limit: int = 5):
    """预览表的前几行数据"""
    try:
        conn = _get_conn(req)
        cur = conn.cursor()
        cur.execute(f"SELECT * FROM `{table_name}` LIMIT {min(limit, 20)}")
        rows = cur.fetchall()
        # 获取列名
        col_names = [desc[0] for desc in cur.description] if cur.description else []
        cur.close()
        conn.close()
        return {
            "table": table_name,
            "columns": col_names,
            "rows": [dict(zip(col_names, [str(v) if v is not None else None for v in row])) for row in rows],
        }
    except Exception as e:
        raise HTTPException(400, f"获取数据预览失败: {str(e)}")
