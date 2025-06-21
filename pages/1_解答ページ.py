# pages/1_解答ページ.py (AI採点・スコア機能付き)

import streamlit as st
import sqlite3
import json
from openai import OpenAI

# ★変更: init_dbを管理者ページと完全に同じ定義にする
def init_db():
    conn = sqlite3.connect('qa.db')
    cursor = conn.cursor()
    # questionsテーブルの完全な定義
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, question_type TEXT NOT NULL, 
        question_text TEXT NOT NULL, options TEXT, answers TEXT NOT NULL, 
        explanation TEXT, difficulty TEXT, points INTEGER, 
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    # answers_historyテーブルの完全な定義
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS answers_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL, 
        question_id INTEGER NOT NULL, user_answer TEXT NOT NULL, 
        is_correct BOOLEAN NOT NULL, awarded_score INTEGER, feedback TEXT,
        answered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (question_id) REFERENCES questions (id)
    )
    ''')
    # ★新規: フィードバックを保存するテーブルを追加
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS test_feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        satisfaction_rating INTEGER,
        free_text_comment TEXT,
        submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    conn.commit()
    conn.close()

# --- AIによる自由記述採点 ---
try:
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
except:
    st.error("解答ページのAPIキー設定に問題があります。")
    st.stop()

# ★新規: フィードバックをDBに保存する関数
def save_test_feedback(user_id, rating, comment):
    conn = sqlite3.connect('qa.db'); cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO test_feedback (user_id, satisfaction_rating, free_text_comment) VALUES (?, ?, ?)",
        (user_id, rating, comment)
    )
    conn.commit(); conn.close()

def grade_free_text_answer(question, user_answer, model_answer, points):
    try:
        prompt = f"""
        あなたは公正な採点者です。以下の問題と模範解答を参考に、学生の解答を採点してください。

        # 問題
        {question}

        # 模範解答
        {model_answer}

        # 学生の解答
        {user_answer}

        # 採点基準
        - この問題は{points}点満点です。
        - 模範解答の要点をどの程度満たしているかに基づいて、0点から{points}点の間で部分点を考慮して採点してください。
        - 採点理由を具体的に記述してください。

        # 出力形式 (必ずこのJSON形式で出力してください)
        {{
          "score": <採点結果の点数(整数)>,
          "feedback": "<採点理由>"
        }}
        """
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": "You are a fair grader."}, {"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        result = json.loads(response.choices[0].message.content)
        return result.get("score", 0), result.get("feedback", "フィードバックが生成されませんでした。")
    except Exception as e:
        return 0, f"AI採点中にエラーが発生しました: {e}"

# --- DB関連の関数 ---
def get_all_questions():
    conn = sqlite3.connect('qa.db'); cursor = conn.cursor()
    # ▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼ 修正箇所 ▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼
    # 不足していた answers と explanation を取得するように修正
    cursor.execute("SELECT id, question_type, question_text, options, points, answers, explanation FROM questions ORDER BY id ASC")
    # ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲ 修正箇所 ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲
    questions = cursor.fetchall(); conn.close()
    return questions

def check_multiple_choice(question_id, user_answer, correct_answers, points):
    # (この関数は引数を少し変更)
    is_correct = False
    if question_id.split('_')[0] in ['5択複数選択問題', 'multiple_select']:
        if isinstance(user_answer, list) and set(user_answer) == set(correct_answers): is_correct = True
    else:
        if not isinstance(user_answer, list): user_answer = [user_answer]
        if user_answer == correct_answers: is_correct = True
    return points if is_correct else 0

def save_answer_history(user_id, question_id, user_answer, is_correct, awarded_score, feedback):
    conn = sqlite3.connect('qa.db'); cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO answers_history (user_id, question_id, user_answer, is_correct, awarded_score, feedback) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, question_id, json.dumps(user_answer), is_correct, awarded_score, feedback)
    )
    conn.commit(); conn.close()

# ★新規: 特定ユーザーのフィードバックが既に存在するかチェックする関数
def check_if_feedback_exists(user_id):
    conn = sqlite3.connect('qa.db'); cursor = conn.cursor()
    # test_feedbackテーブルから指定したuser_idのレコードを1件だけ探す
    cursor.execute("SELECT 1 FROM test_feedback WHERE user_id = ? LIMIT 1", (user_id,))
    exists = cursor.fetchone() is not None
    conn.close()
    return exists

# ★新規: ログアウト処理を行う関数
def logout():
    """セッション情報を全てリセットしてログアウトする"""
    keys_to_delete = [
        'logged_in', 'current_user', 'page_mode', 
        'current_q_index', 'user_answers', 'test_results', 
        'feedback_submitted', 'last_scored_qid'
    ]
    for key in keys_to_delete:
        if key in st.session_state:
            del st.session_state[key]
    st.rerun()

# ★変更: ログイン状態を管理するフラグを追加
def init_session_state():
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False
    if 'current_user' not in st.session_state:
        st.session_state.current_user = None
    if 'page_mode' not in st.session_state:
        st.session_state.page_mode = 'home'
    if 'current_q_index' not in st.session_state:
        st.session_state.current_q_index = 0
    if 'user_answers' not in st.session_state:
        st.session_state.user_answers = {}
    if 'test_results' not in st.session_state:
        st.session_state.test_results = None
    if 'feedback_submitted' not in st.session_state:
        st.session_state.feedback_submitted = False
    if 'just_submitted_feedback' not in st.session_state:
        st.session_state.just_submitted_feedback = False

# ★新規: ログイン画面を描画する関数
def render_login_view():
    st.title("学習者 ログイン")
    
    username = st.selectbox(
        "あなたの名前を選択してください",
        ("student_A", "student_B"),
        index=None,
        placeholder="名前を選択..."
    )

    if st.button("ログイン", use_container_width=True):
        if username:
            st.session_state.logged_in = True
            st.session_state.current_user = username
            st.rerun()
        else:
            st.warning("名前を選択してください。")

# --- 状態管理のためのセッション初期化 ---
def init_session_state():
    if 'page_mode' not in st.session_state: st.session_state.page_mode = 'home'
    if 'current_q_index' not in st.session_state: st.session_state.current_q_index = 0
    if 'user_answers' not in st.session_state: st.session_state.user_answers = {}
    if 'test_results' not in st.session_state: st.session_state.test_results = None
    # ★追加: 現在のユーザーをセッションで管理
    if 'current_user' not in st.session_state:
        st.session_state.current_user = None
    if 'feedback_submitted' not in st.session_state:
        st.session_state.feedback_submitted = False

# --- UIを描画する各画面の関数 ---

# 1. ホーム画面
def render_home_view():
    st.title("学習ホーム")
    #st.session_state.current_user = st.selectbox(
        #"解答者を選択してください",("student_A", "student_B"), 
        #index=None, placeholder="名前を選択...", key="home_user_selector"
    #)
    if st.session_state.current_user:
        st.write(f"こんにちは、**{st.session_state.current_user}** さん！")
        st.write("挑戦したいテストを選択してください。")

        if st.button("第1回 確認テスト", use_container_width=True, key="start_test_button"):
                st.session_state.just_submitted_feedback = False
                st.session_state.page_mode = 'answering'; st.session_state.current_q_index = 0
                st.session_state.user_answers = {}; st.session_state.test_results = None
                st.session_state.feedback_submitted = False; st.rerun()

    # 採点結果があれば、復習・再挑戦ボタンを表示
    if st.session_state.get('test_results'):
        st.write("---")
        st.write("前回の結果:")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("復習する", use_container_width=True, key="review_from_home_button"):
                st.session_state.page_mode = 'review'
                st.rerun()
        with col2:
            if st.button("再挑戦する", type="primary", use_container_width=True, key="retry_from_home_button"):
                if st.session_state.current_user:
                    st.session_state.just_submitted_feedback = False
                    st.session_state.page_mode = 'answering'
                    st.session_state.current_q_index = 0
                    st.session_state.user_answers = {}
                    st.session_state.test_results = None
                    st.rerun()
                else:
                    st.warning("再挑戦する解答者を選択してください。")

# 2. 解答画面
def render_answering_view(questions):
    q_index = st.session_state.current_q_index
    q_id, q_type, q_text, q_options_json, q_points, _, _ = questions[q_index]

    st.subheader(f"問題 {q_index + 1} / {len(questions)} ({q_points}点)")
    st.markdown(f"##### {q_text}")

    # 解答ウィジェット
    user_answer = None
    if q_type in ["4択問題", "5択複数選択問題"] and q_options_json:
        options = json.loads(q_options_json)
        if q_type == '4択問題': user_answer = st.radio("解答:", options, index=None, key=f"q_{q_id}")
        else: user_answer = st.multiselect("解答:", options, key=f"q_{q_id}")
    elif q_type == "自由記述問題": user_answer = st.text_area("解答:", key=f"q_{q_id}")

    # --- ボタンのロジック ---
    is_last_question = (q_index == len(questions) - 1)
    
    # 最終問題の場合、ボタンの文言を動的に変更
    if is_last_question:
        user_id = st.session_state.get('current_user')
        # 既にフィードバック済み（＝再挑戦）かチェック
        if check_if_feedback_exists(user_id):
            button_text = "結果を見る"
        else:
            button_text = "フィードバックに進む"
    else:
        button_text = "次の問題へ"
    
    if st.button(button_text):
        if user_answer is not None and user_answer != "" and user_answer != []:
            # 解答を保存
            st.session_state.user_answers[q_id] = user_answer
            
            if is_last_question:
                # 最終問題の場合、フィードバック済みかチェック
                user_id = st.session_state.get('current_user')
                if check_if_feedback_exists(user_id):
                    # 既にフィードバック済みなら、直接採点して結果表示へ
                    with st.spinner("全問を採点中です..."):
                        grade_all_answers(questions, user_id)
                    st.session_state.page_mode = 'results'
                else:
                    # 未フィードバックなら、フィードバック画面へ
                    st.session_state.page_mode = 'feedback'
                st.rerun()
            else:
                st.session_state.current_q_index += 1; st.rerun()
        else:
            st.warning("解答を選択または入力してください。")

# ★新規: フィードバック専用画面の描画関数
def render_feedback_view(questions):
    st.title("フィードバック")
    st.info("最後に、今回のテストに関するご意見をお聞かせください。")

    with st.form("feedback_form"):
        rating = st.radio("今回の講義内容の満足度を5段階で評価してください。", ('⭐', '⭐⭐', '⭐⭐⭐', '⭐⭐⭐⭐', '⭐⭐⭐⭐⭐'), index=4, horizontal=True)
        comment = st.text_area("ご質問・ご感想があれば自由にご記入ください。")
        
        # ★変更: ボタンを押したら採点処理が始まる
        submitted = st.form_submit_button("フィードバックを送信して結果を見る")
        if submitted:
            # 現在のセッションで認識されているユーザーIDを取得
            #user_id = st.session_state.get('current_user', 'unknown_user')
            
            # 画面にデバッグ情報を表示
            #st.info(f"【デバッグ情報】 '{user_id}' のフィードバックとして保存します。")
            
            rating_value = len(rating)
            user_id = st.session_state.get('current_user', 'unknown_user')
            
            # 1. フィードバックを保存
            save_test_feedback(user_id, rating_value, comment)
            
            # 2. 一括採点を実行
            with st.spinner("全問を採点中です..."):
                grade_all_answers(questions, user_id)
            
            # 3. 結果表示画面へ遷移
            st.session_state.just_submitted_feedback = True
            st.session_state.page_mode = 'results'
            st.rerun()

# 3. 結果表示画面
def render_results_view():
    st.title("テスト結果")
    if st.session_state.get('just_submitted_feedback', False):
        st.success("フィードバックのご協力、ありがとうございました！")
        # メッセージを表示したら、すぐにフラグをリセットして次回以降は表示しない
        st.session_state.just_submitted_feedback = False
    
    results = st.session_state.get('test_results', {})
    total_score = results.get('total_score', 0)
    max_score = results.get('max_score', 0)

    st.header(f"合計点: {total_score} / {max_score} 点")

    if total_score == max_score:
        st.balloons()
        st.success("満点です！素晴らしい！")
    
    st.write("---")
    st.write("各問題の結果:")
    for q_id, result in results.get('details', {}).items():
        # 点数に応じて表示する記号と色を決定
        if result['is_correct']:
            # is_correct は満点の場合のみ True
            score_symbol = "◎"
            display_func = st.success
        elif result['awarded_score'] > 0:
            score_symbol = "△"
            display_func = st.warning
        else:
            score_symbol = "✕"
            display_func = st.error
            
        display_func(f"問題 {q_id}: {score_symbol} ({result['awarded_score']} / {result['points']} 点)")
    
    st.write("---")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("ホームに戻る", use_container_width=True, key="home_from_results_button"):
            st.session_state.page_mode = 'home'
            st.rerun()
    with col2:
        if st.button("解答を復習する", use_container_width=True, key="review_from_results_button"):
            st.session_state.page_mode = 'review'
            st.rerun()

# 4. 復習画面
def render_review_view():
    st.title("解答の復習")
    results = st.session_state.get('test_results', {})
    
    for q_id, result in results.get('details', {}).items():
        score_status = ""
        if result['is_correct']:
            score_status = "◎ 正解"
        elif result['awarded_score'] > 0:
            score_status = "△ 部分点"
        else:
            score_status = "✕ 不正解"
        
        with st.expander(f"問題 {q_id} ({result['awarded_score']} / {result['points']} 点) - {score_status}"):
            st.markdown(f"**問題:**\n> {result['question_text']}")
            st.info(f"**あなたの解答:** `{result['user_answer']}`")
            st.success(f"**正解/模範解答:** `{', '.join(result['correct_answers'])}`")
             # ▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼ 修正箇所 ▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼
            # .replace処理をf-stringの外で行うように修正
            feedback_text = result.get('feedback', '') or "" # Noneの場合を考慮して空文字に
            formatted_feedback = feedback_text.replace('\n', '\n> ')
            st.markdown(f"**解説/フィードバック:**\n> {formatted_feedback}")
            # ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲ 修正箇所 ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲


    if st.button("ホームに戻る",  key="home_from_review_button"):
        st.session_state.page_mode = 'home'
        st.rerun()

# --- 一括採点ロジック ---
def grade_all_answers(questions, user_id):
    total_score = 0
    max_score = 0
    results_details = {}

    for q in questions:
        q_id, q_type, q_text, _, q_points, q_answers_json, q_explanation = q
        max_score += q_points
        user_answer = st.session_state.user_answers.get(q_id)
        correct_answers = json.loads(q_answers_json)
        
        awarded_score = 0
        feedback = ""

        if user_answer:
            if q_type in ["4択問題", "5択複数選択問題"]:
                awarded_score = check_multiple_choice(f"{q_type}_{q_id}", user_answer, correct_answers, q_points)
                feedback = q_explanation
            elif q_type == "自由記述問題":
                model_answer = correct_answers[0] if correct_answers else ""
                awarded_score, feedback = grade_free_text_answer(q_text, user_answer, model_answer, q_points)
        
        # ★変更: save_answer_historyにuser_idを渡す
        is_correct = awarded_score == q_points
        save_answer_history(user_id, q_id, user_answer, is_correct, awarded_score, feedback)

        total_score += awarded_score
        results_details[q_id] = {
            "question_text": q_text, "user_answer": user_answer,
            "correct_answers": correct_answers, "points": q_points,
            "awarded_score": awarded_score, "is_correct": awarded_score == q_points,
            "feedback": feedback
        }
    
    st.session_state.test_results = {
        "total_score": total_score,
        "max_score": max_score,
        "details": results_details
    }


# --- メインの実行ブロック ---

# 1. セッション状態を初期化
init_db() # 念のため解答者ページでもinit_dbを呼ぶ
init_session_state()

if not st.session_state.get('logged_in'):
    # ログインしていなければ、ログイン画面を表示
    render_login_view()
else:
    # ログイン済みであれば、サイドバーにログアウトボタンとユーザー情報を表示
    st.sidebar.success(f"ログイン中: {st.session_state.current_user}")
    st.sidebar.button("ログアウト", on_click=logout)

    # これまでのメインロジックをここに移動
    all_db_questions = get_all_questions()
    if st.session_state.page_mode == 'home':
        render_home_view()
    elif st.session_state.page_mode == 'answering':
        render_answering_view(all_db_questions)
    elif st.session_state.page_mode == 'feedback':
        render_feedback_view(all_db_questions)
    elif st.session_state.page_mode == 'results':
        render_results_view()
    elif st.session_state.page_mode == 'review':
        render_review_view()
