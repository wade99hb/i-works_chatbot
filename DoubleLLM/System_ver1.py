import streamlit as st
import torch
import pandas as pd
import ollama
import warnings
import pymysql
import time
import itertools
import re
import matplotlib.pyplot as plt
import plotly.express as px

from datetime import datetime

db = pymysql.connect(
	host='localhost',
    port=3306,
    user='root',
    passwd='jeminist1029',
    db='zabbix_ver1',
    charset='utf8'
    )

cursor = db.cursor()

#-------------------------------------------------------------------------
# 특정 column의 특정 값something이 있는 행들을 찾는 sql문을 만드는 함수
def FindSomething(table_name,column_name,something):
  
  table_name = 'history_uint' if table_name == '*' else table_name 
  if column_name=='*' or something=='*':
    return warnings.warn('Given input include '*'')
  sql = f'''
    SELECT *
    FROM {table_name}
    WHERE {column_name} = {something}
  '''
  return sql

#키워드로 hostid 결정
def find_hostid(host_list_df):
  keywords = input("찾고 싶은 서버에 대한 키워드 입력: ")
  rows_contain_keywords = host_list_df[host_list_df['result__name'].str.contains(keywords)]
  print(rows_contain_keywords['result__name'])
  choosen = int(input("원하는 서버의 인덱스 번호를 입력해 주십시오"))
  result = host_list_df.iloc[choosen]['result__hostid']
  print(f"{host_list_df.iloc[choosen]['result__name']}의 hostid는 {result}입니다.")
  return int(result)

def does_it_exist(conn, table,itemid):
    """
    테이블에서 itemid의 존재 여부를 확인합니다.
    존재하면 True, 없으면 False를 반환합니다.
    """
    cur = conn.cursor()
    query = f"""
        SELECT EXISTS(
            SELECT 1
            FROM {table}
            WHERE itemid = {itemid}
        ) AS row_exists;
    """
    cur.execute(query)
    result = cur.fetchone()[0]
    cur.close()
    return bool(result)

def exist_data(conn, itemid):
    """
    itemid가 존재하는 테이블을 확인합니다.
    - history에 있으면 1
    - history_uint에 있으면 2
    - 둘 다 없으면 0을 반환합니다.
    """
    if does_it_exist(conn, 'history',itemid):
        return 1
    elif does_it_exist(conn,'history_uint',itemid):
        return 2
    else:
        return 0
    
    # 1. SQL 문법 검사
def check_sql_syntax(sql):
    try:
        cursor.execute(f"EXPLAIN {sql}")  # SQL 문법 검증
        return True
    except Exception as e:
        print(f"SQL 문법 오류: {e}")
        return False

# 2. itemid와 tablecode 매칭 검사
def make_tablecode_right(sql, dic):
    # itemid 찾기
    itemid_match = re.search(r'itemid\s*=\s*(\d+)', sql)
    table_match = re.search(r'FROM\s+(\w+)', sql, re.IGNORECASE)

    if not itemid_match or not table_match:
        return False, "❌ SQL에서 itemid 또는 테이블명이 없음"

    itemid = itemid_match.group(1)  # 추출된 itemid
    table = table_match.group(1)  # 추출된 테이블명

    # dic에서 올바른 tablecode 찾기
    for key, value in dic.items():
        tablecode, dic_itemid = value.split('_')
        if dic_itemid == itemid:
            expected_table = "history" if tablecode == "1" else "history_uint"
            if expected_table == table:
                return True, sql
            else:
                if sql[57:62] =='_uint': # history를 history_uint라고 잘못 적었을 경우
                    sql = sql[:56]+sql[61:]
                else:
                    sql = sql[:56] + '_uint' + sql[57:]
    return True, sql



# 함수구분선 ----------------------------------------------------------------------------------------------------------
st.set_page_config(page_title="Chatbot Interface", layout="wide")


host_list_df = pd.read_excel("C:\CCraft\i-works\Data\zabbix_host_목록_2.xlsx")

if 'chat_history' not in st.session_state:
    st.session_state['chat_history'] = []

# 왼쪽 컬럼은 사용자 입력을 담당
left_col, right_col = st.columns([1, 3])

#hostid와 hostnamename지정
hostid = 11172
hostname= '고성군 대표홈페이지WEB'

#hostid의 itemid df 생성성
query_from_hostid = FindSomething('items','hostid',hostid)
cursor.execute("SELECT * FROM items LIMIT 1")
items_column_names = [desc[0] for desc in cursor.description]
cursor.execute(query_from_hostid)
result = cursor.fetchall()
df_from_hostid = pd.DataFrame(result, columns=items_column_names)
df_from_hostid = df_from_hostid[['itemid','hostid','name','description']]

# 테이블코드/'name' 붙여놓기
dic = {}
for index, value in enumerate(df_from_hostid['itemid']):
  checker = exist_data(db, value)
  if checker == 1:
    dic[str(df_from_hostid['name'][index])] = '_'.join(('1',str(value)))
  elif checker == 2:
    dic[str(df_from_hostid['name'][index])] = '_'.join(('2',str(value)))


with left_col:

    st.write('### 무엇이든 물어보세요!')
    st.write(f'현재 서버 {hostname}의 hostid는 {hostid}입니다.')

    if st.button('오늘 서버 상태 어때?'):
        st.session_state.chat_history.append(("User", "오늘 서버 상태 어때?"))
        st.session_state.chat_history.append(("Bot", "오늘 서버의 상태는 ~~~이고, 수치 변화는 아래 그래프와 같습니다."))

    USERs_Question = st.text_input("텍스트를 입력하거나 추천질문을 클릭하세요")
    if USERs_Question:
        st.session_state.chat_history.append(("User", USERs_Question, hostid))
        # 여기서부터 응답 프로토콜콜
        #LLM에 실제로 들어갈 프롬프트
        prompt = {
        'Users_Question': USERs_Question,
        'Searchable_infomation' : dic,
        'Time_now' : time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        }

        #LLM에 질문하기
        response = ollama.chat(model='Makint_Query_version5', messages=[
            {
                'role': 'user',
                'content': str(prompt)
            },
        ])

        LLMresult = response['message']['content']

        is_valid_sql = check_sql_syntax(LLMresult)
        is_correct_mapping, SQL_made = make_tablecode_right(LLMresult, dic)
        if is_valid_sql and is_correct_mapping:
            print("SQL 문법과 itemid-tablecode 매칭이 올바름")
        elif is_valid_sql==True and is_correct_mapping==False:
            print("SQL 터짐")

        # 현재 가지고 있는 데이터 테스트 시간을 고려한 임시 시간 할당
        testtime = "'2025-02-20 15:02:59' AND '2025-02-21 15:02:59'"

        if SQL_made[56:61] == '_uint':
          tmp_sql = SQL_made[:117] + testtime
        else:
          tmp_sql = SQL_made[:113] + testtime

        print(tmp_sql)
        # 실제 DB에서 정보 받아옴
        cursor.execute(tmp_sql)
        result = cursor.fetchall()

        df = pd.DataFrame(result,columns=['itemid','value','clock'])

        #불러온 지표의 itemid와 name 파악
        itemid_of_indicator = df.iloc[0,0]
        name_of_indicator =  df_from_hostid.loc[df_from_hostid['itemid'] == itemid_of_indicator, 'name'].iloc[0]

        #df의 총 시간
        timeset = (df.iloc[-1][2]-df.iloc[0][2]).seconds
        df_describe= df['value'].describe()

        Answer_describe = f"""
        {timeset//60//60}시간 {timeset//60%60}분 동안의 {name_of_indicator}에 대한 지표는 다음과 같습니다.\n
        평균: {df_describe[1]} | 표준편차: {df_describe[2]} | 최대값: {df_describe[7]} | 최소값: {df_describe[3]} \n
        구체적인 지표 변화는 아래 그래프와 같습니다.
        """

        #불러온 지표의 단위가 있으면 불러옴
        unit_of_pointer_sql = f"""
        SELECT units
        FROM items
        WHERE itemid = {itemid_of_indicator}
        """

        cursor.execute(unit_of_pointer_sql)
        unit_of_pointer = cursor.fetchall()
        fig = px.line(df, x = 'clock', y = 'value')
        st.session_state.chat_history.append(("Bot", Answer_describe, fig))
        

with right_col:
    st.write('### 대화 기록')
    for sender, message, fig in st.session_state.chat_history:
        if sender == 'User':
            st.write(f"**{sender}:** {message}")
        else:
            st.write(f"**{sender}:** {message}")
            st.plotly_chart(fig)
