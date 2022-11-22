import mysql.connector
from mysql.connector import errorcode

from config import Config
from log import log

# 连接MySQL, 获得db_cnx和db_cursor
try:
    db_cnx = mysql.connector.connect(**Config.MYSQL_CONFIG)
    db_cursor = db_cnx.cursor()
except mysql.connector.Error as err:
    if err.errno == errorcode.ER_ACCESS_DENIED_ERROR:
        err_msg = 'Something is wrong with your user name or password'
        log.error(err_msg)
        print(err_msg)
    elif err.errno == errorcode.ER_BAD_DB_ERROR:
        err_msg = 'Database does not exist'
        log.error(err_msg)
        print(err)
    else:
        log.error(err)
        print(err)
    exit(1)

# 在这里手写sql
limit_query_sql = 'select time_limit, memory_limit from problem where id = %s'
update_submission_sql = 'update submission set status = %s, time_cost = %s, memory_cost = %s where id = %s'
update_status_sql = 'update submission set status = %s where id = %s'
inc_submit_sql = 'update problem set submit_num = submit_num + 1 where id = %s'
inc_submit_and_ac_sql = 'update problem set submit_num = submit_num + 1, ac_num = ac_num + 1 where id = %s'
add_passed_record_sql = 'insert into user_problem_passed(username, problem_id) values (%s, %s)'
inc_solved_sql = 'update user set solved = solved + 1 where username = %s'


def get_limits(problem_id):
    try:
        db_cursor.execute(limit_query_sql, (problem_id,))
        return db_cursor.fetchone() or (None, None)
    except mysql.connector.Error as err:
        log.error(err)
        db_cnx.rollback()


def update_submission(submission_id, status, time_cost=None, memory_cost=None):
    try:
        if time_cost is None and memory_cost is None:
            db_cursor.execute(update_status_sql, (status, submission_id))
        else:
            if time_cost is None:
                time_cost = -1
            if memory_cost is None:
                memory_cost = -1
            db_cursor.execute(update_submission_sql,
                              (status, time_cost, memory_cost, submission_id))
        db_cnx.commit()
    except mysql.connector.Error as err:
        log.error(err)
        db_cnx.rollback()


def inc_submit_num(problem_id):
    try:
        db_cursor.execute(inc_submit_sql, (problem_id,))
        db_cnx.commit()
    except mysql.connector.Error as err:
        log.error(err)
        db_cnx.rollback()


def inc_submit_and_ac_num(problem_id):
    try:
        db_cursor.execute(inc_submit_and_ac_sql, (problem_id,))
        db_cnx.commit()
    except mysql.connector.Error as err:
        log.error(err)
        db_cnx.rollback()


def add_passed_record(username, problem_id):
    try:
        db_cursor.execute(add_passed_record_sql, (username, problem_id))
        db_cursor.execute(inc_solved_sql, (username,))
        db_cnx.commit()
    except mysql.connector.Error as err:
        log.error(err)
        db_cnx.rollback()
