import pyodbc
import logging
try:
    # SQL Server connection
    conn_sql = pyodbc.connect('DRIVER={SQL Server};SERVER=ict320-task3a.database.windows.net;DATABASE=joe-pizzeria;UID=student320;PWD=ICT320_student;')

    # Create a cursor for executing SQL queries
    cursor_sql = conn_sql.cursor()

    # Execute a SELECT query to fetch all rows from the "orders" table
    cursor_sql.execute('SELECT * FROM pizza.summary')

    # Fetch all rows from the cursor
    rows = cursor_sql.fetchall()

    # Process the rows
    for row in rows:
        print(row)

    # Close the SQL Server cursor and connection
    cursor_sql.close()
    conn_sql.close()

except Exception as e:
    logging.error(f"Database Connection Error: {e}")
    raise
