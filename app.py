import streamlit as st
import os
from dotenv import load_dotenv
import mysql.connector
import json

st.set_page_config(
    page_title="Kongdon Ramzy",
    layout="wide"
)

load_dotenv()
rds_host = "RDS ENDPOINT"  # RDS 엔드포인트
db_username = "DB_USERNAME"
db_password = "DB_PASSWORD"
db_name = "DB_NAME"

def init_connection():
    """MySQL 연결 초기화 함수"""
    if "connection" not in st.session_state:
        try:
            st.session_state.connection = mysql.connector.connect(
                host=rds_host,
                port="3306",
                user=db_username,
                password=db_password,
                database=db_name
            )
            st.session_state.cursor = st.session_state.connection.cursor()
            st.session_state.connection_open = True
        except mysql.connector.Error as err:
            st.session_state.connection_open = False
            st.error(f"MySQL 연결 오류: {err}")
            
# 사용자가 소속된 그룹 이름 가져오기
def get_group_name(group_ids):
    placeholders = ', '.join(['%s'] * len(group_ids))
    query = f"SELECT groupName FROM `group` WHERE groupId IN ({placeholders})"
    
    try:
        st.session_state.cursor.execute(query, tuple(group_ids) if isinstance(group_ids, list) else (group_ids,))
        groups = st.session_state.cursor.fetchall()
        return [group[0] for group in groups]
    except mysql.connector.Error as err:
        st.error(f"쿼리 실행 중 오류 발생: {err}")
        return []

#글 작성
def create_post_popup():
    """팝업 폼을 통해 게시물 작성"""
    with st.form("post_form", clear_on_submit=True):
        st.text_input("제목", key="new_post_title")
        st.text_area("내용", key="new_post_content")
        st.file_uploader("이미지 업로드", type=["jpg", "png", "jpeg"], key="new_post_image")
        
        # 그룹 선택
        group_options = st.session_state.user['groupNames']
        group_selection = st.selectbox("그룹 선택", group_options, key="new_post_group")

        # 제출 버튼
        submitted = st.form_submit_button("게시물 작성")
        if submitted:
            # 이미지 처리 및 URL 생성
            image = st.session_state.new_post_image
            if image:
                image_url = f"uploaded_images/{image.name}"
                with open(image_url, "wb") as f:
                    f.write(image.getbuffer())
                
                # Save image URL to RDS in JSON format
                save_image_url_to_rds(image_url)
            else:
                # Default image if no image is uploaded
                image_url = "default_image.jpg"
                save_image_url_to_rds(image_url)

            # Group ID
            group_id = st.session_state.user['groupId'][group_options.index(group_selection)]

            # SQL insert query
            query = """
                INSERT INTO post (groupId, userName, foodImage, postTitle, postContent)
                VALUES (%s, %s, JSON_ARRAY(%s), %s, %s)
            """
            values = (
                group_id,
                st.session_state.user['userName'],
                image_url,
                st.session_state.new_post_title,
                st.session_state.new_post_content
            )

            try:
                # Execute the query and commit the transaction
                st.session_state.cursor.execute(query, values)
                st.session_state.connection.commit()
                st.success("게시물이 성공적으로 작성되었습니다.")
            except mysql.connector.Error as err:
                st.error(f"게시물 작성 중 오류 발생: {err}")

def save_image_url_to_rds(image_url):
    try:
        # URL을 JSON 형식으로 변환
        json_data = json.dumps({"url": image_url})
        
        
        conn = mysql.connector.connect(
            host=rds_host,
            port="3306",
            user=db_username,
            password=db_password,
            database=db_name
        )
        cursor = conn.cursor()
        # JSON 형식의 데이터를 RDS에 삽입
        cursor.execute("INSERT INTO post (foodImage) VALUES (%s)", (json_data,))
        conn.commit()
        cursor.close()
        conn.close()
        
        print("이미지 URL이 JSON 형식으로 RDS에 저장되었습니다.")
    except Exception as e:
        print(f"RDS에 저장 실패: {e}")
        
# 사용자 그룹 ID 업데이트
def update_user_group_ids(user_id, new_group_id):
    if not st.session_state.connection_open:
        st.error("MySQL 연결이 끊어졌습니다.")
        return False

    try:
        # 현재 사용자의 groupId 가져오기
        query = "SELECT groupId FROM users WHERE userId = %s"
        st.session_state.cursor.execute(query, (user_id,))
        current_group_ids = st.session_state.cursor.fetchone()[0]
        current_group_ids = json.loads(current_group_ids)

        # 새 그룹 ID 추가
        current_group_ids.append(new_group_id)

        # 업데이트된 groupId를 JSON 형식으로 변환
        updated_group_ids = json.dumps(current_group_ids)

        # 사용자 정보 업데이트
        query = "UPDATE users SET groupId = %s WHERE userId = %s"
        st.session_state.cursor.execute(query, (updated_group_ids, user_id))
        st.session_state.connection.commit()

        st.success(f"사용자 그룹 ID가 성공적으로 업데이트되었습니다! 업데이트된 그룹 ID: {updated_group_ids}")
        return True

    except mysql.connector.Error as err:
        st.error(f"사용자 그룹 ID 업데이트 중 오류 발생: {err}")
        return False

# 그룹 생성 페이지
def create_group_page():
    st.title("그룹 생성하기")

    group_name = st.text_input("그룹 이름")

    if st.button("그룹 생성"):
        if group_name:
            new_group_id = create_group(group_name)
            if new_group_id:
                update_user_group_ids(st.session_state.user['userId'], new_group_id)
                st.session_state.user['groupNames'] = get_group_name(st.session_state.user['groupId'])  # 그룹 이름 갱신
                st.success("그룹 생성 완료!")
        else:
            st.error("그룹 이름을 입력해주세요.")

# 그룹 생성 함수
def create_group(group_name):
    if not st.session_state.connection_open:
        st.error("MySQL 연결이 끊어졌습니다.")
        return None

    try:
        query = "INSERT INTO group (groupName, groupMember) VALUES (%s, %s)"
        username = st.session_state.user['userName']
        st.session_state.cursor.execute(query, (group_name, username))
        st.session_state.connection.commit()

        # 새로 생성된 그룹의 ID 가져오기
        query = "SELECT LAST_INSERT_ID()"
        st.session_state.cursor.execute(query)
        new_group_id = st.session_state.cursor.fetchone()[0]

        st.success(f"그룹 '{group_name}'이(가) 성공적으로 생성되었습니다! 그룹 ID: {new_group_id}")
        return new_group_id
    except mysql.connector.Error as err:
        st.error(f"그룹 생성 중 오류 발생: {err}")
        return None
        
def show_post_details(post):
    """Display detailed view of the post in a full-page style"""
    st.title(post[4])
    st.image(json.loads(post[3])["url"], use_container_width=True)
    st.write(post[5])
    st.write(f"By: {post[2]}")
    if st.button("Back"):
        st.session_state.selected_post = None

# 로그인 인증
def login_process(user_id, password):
    if not st.session_state.connection_open:
        st.error("MySQL 연결이 끊어졌습니다.")
        return False

    try:
        # 사용자 인증을 위한 SQL 쿼리
        query = "SELECT * FROM users WHERE userId = %s AND userPw = %s"
        st.session_state.cursor.execute(query, (user_id, password))
        user = st.session_state.cursor.fetchone()

        # 사용자가 존재하면
        if user:
            st.session_state.user = {
                'userId': user[0],
                'groupId': json.loads(user[2]),
                'userName': user[3],
                'groupNames': get_group_name(json.loads(user[2]))
            }
            return True
        return False
    except mysql.connector.Error as err:
        st.error(f"쿼리 실행 중 오류 발생: {err}")
        return False

# 로그인 페이지
def login():
    st.markdown(
        """
        <style>
        .banner {
            width: 100%;
            height: 150px;  /* 배너의 높이 */
            object-fit: cover; /* 이미지가 자르도록 설정 */
            margin-bottom: 20px; /* 배너 아래 간격 */
        }
        </style>
        <img src="https://berrysoup.ca/Images/Desktop4.jpg" class="banner" alt="Login Banner">
        """, unsafe_allow_html=True
    )
    st.title("Login")

    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    
    if st.button("Login"):
        if login_process(username, password):
            st.session_state.logged_in = True
        else:
            st.session_state.logged_in = False
            st.error("잘못된 사용자 이름 또는 비밀번호입니다.")
    st.button("Register")

init_connection()

def main():
    # 사이드바 네비게이션
    st.sidebar.markdown(
        f"""
        <style>
        .profile-pic {{
            width: 80px;
            height: 80px;
            border-radius: 50%;
            margin: 0 auto;
            display: block;
        }}
        .username {{
            text-align: center;
            font-size: 1.2em;
            font-weight: bold;
            margin: 10px 0;
        }}
        .group-list {{
            list-style-type: none;
            padding: 0;
            margin: 0;
        }}
        .group-list li {{
            padding: 8px 0;
            border-bottom: 1px solid #ddd;
        }}
        </style>
        <div style="text-align: center;">
            <img src="https://images.vexels.com/media/users/3/147101/isolated/preview/b4a49d4b864c74bb73de63f080ad7930-instagram-profile-button.png" class="profile-pic" alt="Profile Image">
        </div>
        <div class="username">{st.session_state.user['userName']}님</div>
        """, unsafe_allow_html=True)

    st.sidebar.markdown("---")

    selected_group = None
    if st.sidebar.button("All"):
        selected_group = None

    # 그룹 리스트 출력
    st.sidebar.markdown("### 가입한 그룹")
    groups = st.session_state.user['groupNames']
    for group in groups:
        if st.sidebar.button(group):
            selected_group = group

    st.sidebar.markdown("---")

    # 그룹 생성하기 버튼
    if st.sidebar.button("그룹 생성하기"):
        create_group_page()
        return
    
    if st.sidebar.button("새 게시물 작성하기"):
        create_post_popup()
        return

    # 메인 화면 콘텐츠
    st.title("Latest Posts")

    # 선택된 그룹의 groupId 가져오기
    if selected_group:
        # 그룹 선택 시 해당 groupId 찾기
        for group in groups:
            if group == selected_group:
                query = "SELECT groupId FROM `group` WHERE groupName = %s"
                st.session_state.cursor.execute(query, (group,))
                result = st.session_state.cursor.fetchone()
                if result:
                    selected_group_id = result[0]
    else:
        selected_group_id = None

    # 게시글 필터링
    if selected_group:
        query = "SELECT * FROM post WHERE groupId = %s ORDER BY postId DESC"
        st.session_state.cursor.execute(query, (selected_group_id,))
        posts = st.session_state.cursor.fetchall()
    else:
        user_group_ids = st.session_state.user['groupId']
        placeholders = ', '.join(['%s'] * len(user_group_ids))
        query = f"SELECT * FROM post WHERE groupId IN ({placeholders}) ORDER BY postId DESC"
        st.session_state.cursor.execute(query, tuple(user_group_ids))
        posts = st.session_state.cursor.fetchall()

   # 상세보기 화면인지 확인하고 렌더링
    if "selected_post" in st.session_state and st.session_state.selected_post:
        show_post_details(st.session_state.selected_post)  # 상세보기 화면 표시
    else:
        
        st.markdown(
            """
            <style>
            .square-button {
                display: inline-block;
                width: 30px; /* Set width to control size */
                height: 30px; /* Set height to make it a square */
                background-color: #c4c4c4; /* Set button color */
                color: white;
                border: none;
                border-radius: 5px; /* Optional: rounded corners */
                text-align: center;
                font-size: 16px;
                cursor: pointer;
            }
            </style>
            """,
            unsafe_allow_html=True
        )   

        # 게시글 목록 화면 표시
        columns = st.columns(4)
        post_counter = 0
        for post in posts:
            column = columns[post_counter % 4]
            with column:
                foodImage = json.loads(post[3])
                foodImage_url = foodImage["url"]
        
                st.image(foodImage_url, use_container_width=True)
                st.subheader(post[4]) 
                st.write(post[5][:100] + "...")
              
                author_col, button_col = st.columns([3, 1])
                with author_col:
                    st.write(f"By: {post[2]}")
                with button_col:
                    if st.button(" ", key=f"post_{post[0]}"):
                        st.session_state.selected_post = post
        
            post_counter += 1


if "logged_in" not in st.session_state:
    st.session_state.logged_in = False


if st.session_state.logged_in:
    main()
else:
    login()
