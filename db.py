import os
import psycopg2
from psycopg2.extras import RealDictCursor

SUPABASE_URL = os.environ.get("SUPABASE_URL")

def get_connection():
    """Get a connection to the Supabase PostgreSQL database."""
    if not SUPABASE_URL:
        raise ValueError("SUPABASE_URL environment variable not set")
    
    return psycopg2.connect(SUPABASE_URL, cursor_factory=RealDictCursor)

def test_connection():
    """Test the database connection."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        result = cur.fetchone()
        cur.close()
        conn.close()
        return True, "Connection successful"
    except Exception as e:
        return False, str(e)

def execute_query(query: str, params: tuple = None):
    """Execute a query and return results."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(query, params)
        
        if cur.description:
            results = cur.fetchall()
            columns = [desc[0] for desc in cur.description]
            return {"columns": columns, "data": results}
        else:
            conn.commit()
            return {"affected_rows": cur.rowcount}
    finally:
        cur.close()
        conn.close()

def get_tables():
    """Get list of tables in the database."""
    query = """
    SELECT table_name 
    FROM information_schema.tables 
    WHERE table_schema = 'public'
    ORDER BY table_name;
    """
    result = execute_query(query)
    return [row["table_name"] for row in result.get("data", [])]

def get_table_schema(table_name: str):
    """Get schema for a specific table."""
    query = """
    SELECT column_name, data_type, is_nullable
    FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = %s
    ORDER BY ordinal_position;
    """
    return execute_query(query, (table_name,))
