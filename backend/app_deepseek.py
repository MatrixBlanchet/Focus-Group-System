from flask import Flask, request, jsonify, session, make_response
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
import requests
import json
import time
import random
import hashlib
import uuid
from datetime import datetime

import os
basedir = os.path.abspath(os.path.dirname(__file__))

from io import BytesIO
from urllib.parse import quote
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import platform

app = Flask(__name__, static_folder='static')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'focus_group.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JSON_AS_ASCII'] = False
app.config['JSONIFY_MIMETYPE'] = 'application/json; charset=utf-8'
app.secret_key = 'your-secret-key-here-make-it-very-long-and-secret-for-production'
db = SQLAlchemy(app)
CORS(app)

with open('config.txt', 'r') as f:
    for line in f:
        if line.startswith('DEEPSEEK_API_KEY='):
            DEEPSEEK_API_KEY = line.split('=', 1)[1].strip()
        elif line.startswith('DEEPSEEK_BASE_URL='):
            DEEPSEEK_BASE_URL = line.split('=', 1)[1].strip()
        elif line.startswith('MODEL='):
            MODEL = line.split('=', 1)[1].strip()

class ProductScenario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    product_name = db.Column(db.String(100), nullable=False)
    product_concept = db.Column(db.Text, nullable=False)
    core_selling_points = db.Column(db.Text, nullable=False)
    discussion_topics = db.Column(db.Text, nullable=False)
    occasion_type = db.Column(db.String(50), nullable=False, default='focus_group')
    occasion_description = db.Column(db.Text, nullable=False, default='标准焦点小组讨论')
    created_at = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'product_name': self.product_name,
            'product_concept': self.product_concept,
            'core_selling_points': json.loads(self.core_selling_points),
            'discussion_topics': json.loads(self.discussion_topics),
            'occasion_type': self.occasion_type,
            'occasion_description': self.occasion_description,
            'created_at': self.created_at.isoformat()
        }

class VirtualParticipant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    scenario_id = db.Column(db.Integer, db.ForeignKey('product_scenario.id'), nullable=False)
    persona_name = db.Column(db.String(50), nullable=False)
    persona_tags = db.Column(db.Text, nullable=False)
    personality = db.Column(db.Text, nullable=False)
    background = db.Column(db.Text, nullable=False)
    is_custom = db.Column(db.Boolean, default=False)
    is_ai_generated = db.Column(db.Boolean, default=False)

    def to_dict(self):
        return {
            'id': self.id,
            'scenario_id': self.scenario_id,
            'persona_name': self.persona_name,
            'persona_tags': json.loads(self.persona_tags),
            'personality': self.personality,
            'background': self.background,
            'is_custom': self.is_custom,
            'is_ai_generated': self.is_ai_generated
        }

class ConversationRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    scenario_id = db.Column(db.Integer, db.ForeignKey('product_scenario.id'), nullable=False)
    participant_id = db.Column(db.Integer, nullable=False)
    content = db.Column(db.Text, nullable=False)
    is_host = db.Column(db.Boolean, default=False)
    message_type = db.Column(db.String(20), default='normal')
    timestamp = db.Column(db.DateTime, default=datetime.now)

class AnalysisReport(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    scenario_id = db.Column(db.Integer, db.ForeignKey('product_scenario.id'), nullable=False)
    report_title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    generated_at = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        return {
            'id': self.id,
            'scenario_id': self.scenario_id,
            'report_title': self.report_title,
            'content': self.content,
            'generated_at': self.generated_at.isoformat()
        }

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'created_at': self.created_at.isoformat()
        }

def call_deepseek(prompt, system_prompt="你是一个有帮助的AI助手", max_retries=3):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}"
    }

    data = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.8,
        "max_tokens": 1500
    }

    retry_delay = 2  
    last_error = None

    for attempt in range(max_retries):
        try:
            response = requests.post(
                f"{DEEPSEEK_BASE_URL}/chat/completions",
                headers=headers,
                json=data,
                timeout=30
            )

            if response.status_code == 200:
                return response.json()["choices"][0]["message"]["content"]
            elif response.status_code in [429, 500, 502, 503, 504]:
                last_error = f"API Error {response.status_code}: 服务暂时不可用，正在重试..."
                print(f"第 {attempt + 1} 次请求失败，状态码: {response.status_code}，{last_error}")
            else:
                return f"API Error: {response.status_code} - {response.text}"
        except requests.exceptions.RequestException as e:
            last_error = f"Request Error: {str(e)}"
            print(f"第 {attempt + 1} 次请求失败，{last_error}")

        if attempt < max_retries - 1:
            time.sleep(retry_delay * (attempt + 1))

    return last_error or "请求失败，请稍后重试"

@app.route('/')
def index():
    return app.send_static_file('index.html')

@app.route('/report')
def report():
    return app.send_static_file('report.html')

@app.route('/api/scenarios', methods=['POST'])
def create_scenario():
    try:
        user_id = session.get('user_id')
        if not user_id:
            return app.response_class(
                response=json.dumps({"error": "请先登录"}, ensure_ascii=False),
                status=401,
                mimetype='application/json; charset=utf-8'
            )
        
        data = request.json
        scenario = ProductScenario(
            user_id=user_id,
            product_name=data['product_name'],
            product_concept=data['product_concept'],
            core_selling_points=json.dumps(data['core_selling_points'], ensure_ascii=False),
            discussion_topics=json.dumps(data['discussion_topics'], ensure_ascii=False),
            occasion_type=data.get('occasion_type', 'focus_group'),
            occasion_description=data.get('occasion_description', '标准焦点小组讨论')
        )
        db.session.add(scenario)
        db.session.commit()
        result = scenario.to_dict()
        return app.response_class(
            response=json.dumps(result, ensure_ascii=False),
            status=201,
            mimetype='application/json; charset=utf-8'
        )
    except Exception as e:
        return app.response_class(
            response=json.dumps({'error': str(e)}, ensure_ascii=False),
            status=500,
            mimetype='application/json; charset=utf-8'
        )

@app.route('/api/scenarios', methods=['GET'])
def get_scenarios():
    user_id = session.get('user_id')
    if not user_id:
        return app.response_class(
            response=json.dumps({"error": "请先登录"}, ensure_ascii=False),
            status=401,
            mimetype='application/json; charset=utf-8'
        )
    
    scenarios = ProductScenario.query.filter_by(user_id=user_id).all()
    result = [s.to_dict() for s in scenarios]
    return app.response_class(
        response=json.dumps(result, ensure_ascii=False),
        status=200,
        mimetype='application/json; charset=utf-8'
    )

def get_scenario_or_403(id):
    """获取场景，检查是否属于当前用户"""
    user_id = session.get('user_id')
    if not user_id:
        return None, app.response_class(
            response=json.dumps({"error": "请先登录"}, ensure_ascii=False),
            status=401,
            mimetype='application/json; charset=utf-8'
        )
    
    scenario = ProductScenario.query.get(id)
    if not scenario:
        return None, app.response_class(
            response=json.dumps({"error": "场景不存在"}, ensure_ascii=False),
            status=404,
            mimetype='application/json; charset=utf-8'
        )
    
    if scenario.user_id != user_id:
        return None, app.response_class(
            response=json.dumps({"error": "无权访问该场景"}, ensure_ascii=False),
            status=403,
            mimetype='application/json; charset=utf-8'
        )
    
    return scenario, None

@app.route('/api/scenarios/<int:id>', methods=['GET'])
def get_scenario(id):
    scenario, error_response = get_scenario_or_403(id)
    if error_response:
        return error_response
    
    result = scenario.to_dict()
    return app.response_class(
        response=json.dumps(result, ensure_ascii=False),
        status=200,
        mimetype='application/json; charset=utf-8'
    )

@app.route('/api/scenarios/<int:id>/generate-participants', methods=['POST'])
def generate_participants_with_ai(id):
    scenario, error_response = get_scenario_or_403(id)
    if error_response:
        return error_response
    
    data = request.json or {}
    count = data.get('count', 4)
    target_audience = data.get('target_audience', '普通消费者')
    regenerate = data.get('regenerate', False)

    existing_participants = VirtualParticipant.query.filter_by(scenario_id=id).all()
    if existing_participants and not regenerate:
        result = [p.to_dict() for p in existing_participants]
        return app.response_class(
            response=json.dumps(result, ensure_ascii=False),
            status=200,
            mimetype='application/json; charset=utf-8'
        )

    VirtualParticipant.query.filter_by(scenario_id=id).delete()
    db.session.commit()

    occasion_type = scenario.occasion_type
    occasion_desc = scenario.occasion_description or ""

    if occasion_type == "product_team":
        role_type = "企业产品团队成员"
        role_examples = "产品经理、资深研发工程师、用户体验设计师、市场分析师、运营负责人"
        role_desc = "你需要扮演企业内部产品团队成员，从专业角度分析产品"
    elif occasion_type == "sales_conversation":
        role_type = "销售人员"
        role_examples = "销售主管、大客户经理、渠道专员、区域销售代表"
        role_desc = "你需要扮演销售人员，从销售角度探测客户需求"
    elif occasion_type == "focus_group":
        role_type = "目标用户"
        role_examples = "硬核极客、价格敏感型宝妈、颜控女大学生、职场白领、运动爱好者"
        role_desc = "你需要扮演目标用户，表达真实使用体验和需求"
    elif occasion_type == "user_interview":
        role_type = "深度访谈用户"
        role_examples = "资深用户、潜在客户、竞品用户、行业专家"
        role_desc = "你需要扮演被访谈用户，深入表达观点"
    elif occasion_type == "brainstorming":
        role_type = "创意团队成员"
        role_examples = "产品经理、创意总监、市场营销专家、技术骨干、用户研究员"
        role_desc = "你需要扮演创意团队成员，激发创新想法"
    else:
        role_type = "普通消费者"
        role_examples = "普通用户、潜在客户"
        role_desc = "你需要扮演普通消费者"

    prompt = f"""请为【{occasion_desc}】场景生成{count}个专业的{role_type}角色画像，用于产品分析讨论。
要求：
1. 每个角色要有独特的名字、背景、性格特点
2. 背景要具体，包括职业经历、专业领域
3. 性格特点要与背景相符
4. 角色之间要有差异化，适合进行产品讨论

请直接输出JSON数组格式，例如：
[{{"name":"张三","tags":["技术","创新"],"personality":"理性严谨","background":"背景描述"}}]

直接输出JSON数组，不要加任何其他内容。"""

    system_prompt = f"你是一个专业的企业管理顾问，擅长创建真实、专业的职场角色画像。现在需要为【{occasion_desc}】场景生成{count}个{role_type}角色，每个角色必须有明确的职位和专业背景。"

    result = call_deepseek(prompt, system_prompt)

    try:
        personas = json.loads(result)
        if not isinstance(personas, list):
            personas = [personas]
    except:
        personas = [
            {"name": "随机用户A", "tags": ["普通用户"], "personality": "普通用户性格", "background": "普通背景"}
        ]

    participants = []
    for p in personas[:count]:
        participant = VirtualParticipant(
            scenario_id=id,
            persona_name=p.get('name', '未知用户'),
            persona_tags=json.dumps(p.get('tags', ['普通用户']), ensure_ascii=False),
            personality=p.get('personality', '性格未知'),
            background=p.get('background', '背景未知'),
            is_custom=False,
            is_ai_generated=True
        )
        db.session.add(participant)
        participants.append(participant)

    db.session.commit()

    result_data = {
        "status": "success",
        "ai_response": result[:500],
        "participants": [p.to_dict() for p in participants]
    }
    return app.response_class(
        response=json.dumps(result_data, ensure_ascii=False),
        status=200,
        mimetype='application/json; charset=utf-8'
    )

@app.route('/api/scenarios/<int:id>/simulate', methods=['POST'])
def simulate_conversation_with_ai(id):
    scenario, error_response = get_scenario_or_403(id)
    if error_response:
        return error_response
    
    data = request.json or {}
    rounds = data.get('rounds', 3)
    message_count = data.get('message_count', 0)

    participants = VirtualParticipant.query.filter_by(scenario_id=id).all()

    if not participants:
        return app.response_class(
            response=json.dumps({"error": "请先生成参与者"}, ensure_ascii=False),
            status=400,
            mimetype='application/json; charset=utf-8'
        )

    selling_points = json.loads(scenario.core_selling_points)
    topics = json.loads(scenario.discussion_topics)

    ConversationRecord.query.filter_by(scenario_id=id).delete()

    host_intro = ConversationRecord(
        scenario_id=id,
        participant_id=0,
        content=f"好啦，各位朋友大家好！欢迎来参加今天的焦点小组讨论。\n\n今天我们主要想聊聊「{scenario.product_name}」这个产品。\n\n先简单说一下这个产品：{scenario.product_concept}\n\n它主打的卖点是：{','.join(selling_points)}\n\n我们就从第一个话题开始吧：{topics[0]}\n\n大家有什么想法就说什么，不用客气啊！",
        is_host=True,
        message_type='intro'
    )
    db.session.add(host_intro)
    db.session.commit()

    topic_msg = ConversationRecord(
        scenario_id=id,
        participant_id=0,
        content=f"话题 1：{topics[0]}",
        is_host=True,
        message_type='topic'
    )
    db.session.add(topic_msg)
    db.session.commit()

    conversation_history = []

    import random

    if message_count > 0:
        target_count = message_count
        current_count = 0
        participant_index = 0
        
        while current_count < target_count:
            time.sleep(1)
            
            participant = participants[participant_index % len(participants)]
            round_num = current_count // len(participants)
            
            if current_count == 0:
                prompt = f"""想象你就是一个真实的消费者"{participant.persona_name}"，正在参加一个产品讨论会。

你的背景：{participant.persona_name}，{participant.background}
你的性格特点：{participant.personality}
别人对你的印象标签：{','.join(json.loads(participant.persona_tags))}

我们今天在讨论的产品是「{scenario.product_name}」，它的概念是：{scenario.product_concept}
这个产品的核心卖点包括：{','.join(selling_points)}

现在大家正在聊的话题是：{topics[round_num % len(topics)]}

请像平时和朋友聊天一样，说说你对这个产品的看法。可以是你的期待、疑惑、或者你觉得需要改进的地方。用你自己最舒服的方式表达就好，不用刻意组织语言，真实自然一点。
（请控制在50-120字，直接输出你说的话即可）"""

                system_prompt = "你扮演的是一个真实的、有血有肉的消费者，不是AI。在讨论中会自然地流露情感，有时候会有语气词，有时候会说一些看似跑题但实际相关的话。"
            else:
                history_text = "\n".join([f"{h['participant']}：{h['content']}" for h in conversation_history[-8:]])
                interaction_types = ["追问", "反驳", "补充", "同意", "质疑", "举例"]
                interaction_type = random.choice(interaction_types)

                prompt = f"""你"{participant.persona_name}"正在和一个产品团队开会讨论产品。

你的身份背景：{participant.background}
你的性格：{participant.personality}
你的标签：{','.join(json.loads(participant.persona_tags))}

今天讨论的产品是「{scenario.product_name}」：
- 产品概念：{scenario.product_concept}
- 核心卖点：{','.join(selling_points)}

之前的讨论内容：
{history_text}

现在大家正在讨论的话题是：{topics[round_num % len(topics)]}

作为"{participant.persona_name}"，你听了大家的发言后，也想说几句。用你自己的话说，不用拘泥于格式，可以：
- 同意某人的观点并补充
- 提出不同看法
- 分享一个相关的亲身经历
- 问个问题

请自然地参与讨论，60-150字，用口语化的方式表达。"""

                system_prompt = "你扮演的是一个真实的消费者，有自己的观点和情绪。会因为同意别人的话而点头，也会因为不认同的观点而皱眉。说话时会不自觉地带出自己的职业习惯和个人经历。"

            response = call_deepseek(prompt, system_prompt)

            if response.startswith(("API Error", "Request Error", "请求失败")):
                error_responses = [
                    f"这个问题我有点想法...（停顿）嗯，我觉得可以从另一个角度来看待。",
                    f"我这边网络不太稳定，不过关于这个话题，我的看法是...",
                    f"抱歉，刚才信号不太好。我想补充一点，{participant.persona_name}认为这个产品还是很有潜力的。",
                    f"让我整理一下思路...我觉得大家刚才的讨论很有价值。",
                    f"（清了清嗓子）关于这个问题，我想分享一下我的看法。"
                ]
                response = random.choice(error_responses)
                print(f"AI请求失败，使用备用回复: {response}")

            record = ConversationRecord(
                scenario_id=id,
                participant_id=participant.id,
                content=response,
                is_host=False,
                message_type='normal'
            )
            db.session.add(record)
            db.session.commit()

            conversation_history.append({"participant": participant.persona_name, "content": response})
            current_count += 1
            participant_index += 1

            if current_count < target_count and current_count % len(participants) == 0 and len(conversation_history) >= 2:
                time.sleep(1)
                recent_talkers = [h['participant'] for h in conversation_history[-4:]]
                host_prompt = f"""你是这场焦点小组讨论的主持人。刚才发言的朋友们聊得很热烈：

最近发言的朋友：{', '.join(recent_talkers)}

你作为一个有经验的主持人，需要把讨论继续推进下去。不要说太多，自然地引导一下：
- 可以邀请还没怎么发言的朋友说说看法
- 或者针对刚才聊到的某个点，追问一下
- 也可以简单总结一下大家说的方向

请用口语化、亲切的方式说几句，30-60字就够了。就像朋友间聊天那样自然，不要像在做报告。"""

                host_response = call_deepseek(host_prompt, "你是一位亲切自然的主持人，说话不像是在念稿，更像是和一群朋友聊天。语气轻松但专业，能够让每个人都感到舒适和被尊重。")

                if host_response.startswith(("API Error", "Request Error", "请求失败")):
                    host_response = random.choice([
                        "好的，那我们继续下一个话题吧。",
                        "大家说得都很有道理！那接下来..."
                    ])
                    print(f"主持人请求失败，使用备用回复: {host_response}")

                guide_msg = ConversationRecord(
                    scenario_id=id,
                    participant_id=0,
                    content=host_response,
                    is_host=True,
                    message_type='guide'
                )
                db.session.add(guide_msg)
                db.session.commit()
                conversation_history.append({"participant": "主持人", "content": host_response})
    else:
        for round_num in range(rounds):
            time.sleep(1)

            if round_num == 0:
                for participant in participants:
                    time.sleep(1.5)

                    prompt = f"""想象你就是一个真实的消费者"{participant.persona_name}"，正在参加一个产品讨论会。

你的背景：{participant.persona_name}，{participant.background}
你的性格特点：{participant.personality}
别人对你的印象标签：{','.join(json.loads(participant.persona_tags))}

我们今天在讨论的产品是「{scenario.product_name}」，它的概念是：{scenario.product_concept}
这个产品的核心卖点包括：{','.join(selling_points)}

现在大家正在聊的话题是：{topics[round_num % len(topics)]}

请像平时和朋友聊天一样，说说你对这个产品的看法。可以是你的期待、疑惑、或者你觉得需要改进的地方。用你自己最舒服的方式表达就好，不用刻意组织语言，真实自然一点。
（请控制在50-120字，直接输出你说的话即可）"""

                    system_prompt = "你扮演的是一个真实的、有血有肉的消费者，不是AI。在讨论中会自然地流露情感，有时候会有语气词，有时候会说一些看似跑题但实际相关的话。"

                    response = call_deepseek(prompt, system_prompt)

                    if response.startswith(("API Error", "Request Error", "请求失败")):
                        response = random.choice([
                            f"我觉得这个产品挺有意思的，{participant.persona_name}表示很期待。",
                            f"关于这个话题，我有一些想法想分享...",
                            f"嗯，让我想想，我觉得这个产品的定位很清晰。"
                        ])
                        print(f"AI请求失败，使用备用回复: {response}")

                    record = ConversationRecord(
                        scenario_id=id,
                        participant_id=participant.id,
                        content=response,
                        is_host=False,
                        message_type='normal'
                    )
                    db.session.add(record)
                    db.session.commit()

                    conversation_history.append({"participant": participant.persona_name, "content": response})
            else:
                for participant in participants:
                    time.sleep(1.5)

                    history_text = "\n".join([f"{h['participant']}：{h['content']}" for h in conversation_history[-8:]])

                    interaction_types = ["追问", "反驳", "补充", "同意", "质疑", "举例"]
                    interaction_type = random.choice(interaction_types)

                    prompt = f"""你"{participant.persona_name}"正在和一个产品团队开会讨论产品。

你的身份背景：{participant.background}
你的性格：{participant.personality}
你的标签：{','.join(json.loads(participant.persona_tags))}

今天讨论的产品是「{scenario.product_name}」：
- 产品概念：{scenario.product_concept}
- 核心卖点：{','.join(selling_points)}

之前的讨论内容：
{history_text}

现在大家正在讨论的话题是：{topics[round_num % len(topics)]}

作为"{participant.persona_name}"，你听了大家的发言后，也想说几句。用你自己的话说，不用拘泥于格式，可以：
- 同意某人的观点并补充
- 提出不同看法
- 分享一个相关的亲身经历
- 问个问题

请自然地参与讨论，60-150字，用口语化的方式表达。"""

                    system_prompt = "你扮演的是一个真实的消费者，有自己的观点和情绪。会因为同意别人的话而点头，也会因为不认同的观点而皱眉。说话时会不自觉地带出自己的职业习惯和个人经历。"

                    response = call_deepseek(prompt, system_prompt)

                    if response.startswith(("API Error", "Request Error", "请求失败")):
                        response = random.choice([
                            f"我同意刚才那位朋友的看法，{participant.persona_name}也有类似的感受。",
                            f"这个点我想补充一下...",
                            f"（思考了一下）我觉得可以从另一个角度来看这个问题。"
                        ])
                        print(f"AI请求失败，使用备用回复: {response}")

                    record = ConversationRecord(
                        scenario_id=id,
                        participant_id=participant.id,
                        content=response,
                        is_host=False,
                        message_type='normal'
                    )
                    db.session.add(record)
                    db.session.commit()

                    conversation_history.append({"participant": participant.persona_name, "content": response})

            if round_num < rounds - 1 and len(conversation_history) >= 2:
                time.sleep(1)
                recent_talkers = [h['participant'] for h in conversation_history[-4:]]
                host_prompt = f"""你是这场焦点小组讨论的主持人。刚才发言的朋友们聊得很热烈：

最近发言的朋友：{', '.join(recent_talkers)}

你作为一个有经验的主持人，需要把讨论继续推进下去。不要说太多，自然地引导一下：
- 可以邀请还没怎么发言的朋友说说看法
- 或者针对刚才聊到的某个点，追问一下
- 也可以简单总结一下大家说的方向

请用口语化、亲切的方式说几句，30-60字就够了。就像朋友间聊天那样自然，不要像在做报告。"""

                host_response = call_deepseek(host_prompt, "你是一位亲切自然的主持人，说话不像是在念稿，更像是和一群朋友聊天。语气轻松但专业，能够让每个人都感到舒适和被尊重。")

                if host_response.startswith(("API Error", "Request Error", "请求失败")):
                    host_response = random.choice([
                        "好的，那我们继续下一个话题吧。",
                        "大家说得都很有道理！那接下来..."
                    ])
                    print(f"主持人请求失败，使用备用回复: {host_response}")

                guide_msg = ConversationRecord(
                    scenario_id=id,
                    participant_id=0,
                    content=host_response,
                    is_host=True,
                    message_type='guide'
                )
                db.session.add(guide_msg)
                db.session.commit()
                conversation_history.append({"participant": "主持人", "content": host_response})

            if round_num < rounds - 1:
                time.sleep(0.5)
                summary_msg = ConversationRecord(
                    scenario_id=id,
                    participant_id=0,
                    content="好，刚才大家聊得挺好的，我先简单小结一下...（停顿）嗯，总的来说大家对这个产品的功能还是比较认可的，尤其是某某方面...那我们接下来聊聊下一个话题吧。",
                    is_host=True,
                    message_type='summary'
                )
                db.session.add(summary_msg)
                db.session.commit()

    conclusion_msg = ConversationRecord(
        scenario_id=id,
        participant_id=0,
        content="好啦，今天的讨论就到这里吧！非常感谢各位的积极参与，大家聊得都很真实、很深入，给我们提供了很多有价值的意见。等我整理一下今天的讨论，很快就会给大家一份完整的分析报告。辛苦各位了！",
        is_host=True,
        message_type='conclusion'
    )
    db.session.add(conclusion_msg)
    db.session.commit()

    result_data = {
        "status": "success",
        "message": f"对话模拟完成，共{rounds}轮讨论，{len(participants)}位参与者",
        "rounds": rounds,
        "participants_count": len(participants),
        "total_messages": ConversationRecord.query.filter_by(scenario_id=id).count()
    }
    return app.response_class(
        response=json.dumps(result_data, ensure_ascii=False),
        status=200,
        mimetype='application/json; charset=utf-8'
    )

@app.route('/api/scenarios/<int:id>/conversation', methods=['GET'])
def get_conversation(id):
    _, error_response = get_scenario_or_403(id)
    if error_response:
        return error_response
    
    records = ConversationRecord.query.filter_by(scenario_id=id).order_by(ConversationRecord.timestamp).all()

    participants = VirtualParticipant.query.filter_by(scenario_id=id).all()
    participant_map = {p.id: p.persona_name for p in participants}
    participant_map[0] = "AI主持人"

    result = []
    for record in records:
        if record.participant_id == -1:
            participant_name = "我"
        else:
            participant_name = participant_map.get(record.participant_id, "未知")

        result.append({
            "id": record.id,
            "participant_id": record.participant_id,
            "participant_name": participant_name,
            "content": record.content,
            "timestamp": record.timestamp.isoformat(),
            "is_host": record.is_host,
            "message_type": record.message_type
        })

    return app.response_class(
        response=json.dumps(result, ensure_ascii=False),
        status=200,
        mimetype='application/json; charset=utf-8'
    )

@app.route('/api/scenarios/<int:id>/conversation', methods=['POST'])
def add_message(id):
    scenario, error_response = get_scenario_or_403(id)
    if error_response:
        return error_response
    
    data = request.get_json()
    content = data.get('content', '').strip()
    participant_name = data.get('participant_name', '我')

    if not content:
        return app.response_class(
            response=json.dumps({"error": "消息内容不能为空"}, ensure_ascii=False),
            status=400,
            mimetype='application/json; charset=utf-8'
        )

    participants = VirtualParticipant.query.filter_by(scenario_id=id).all()
    
    if not participants:
        return app.response_class(
            response=json.dumps({"error": "该场景没有参与者"}, ensure_ascii=False),
            status=400,
            mimetype='application/json; charset=utf-8'
        )

    record = ConversationRecord(
        scenario_id=id,
        participant_id=-1,
        content=content,
        is_host=False,
        message_type='user'
    )
    db.session.add(record)
    db.session.commit()

    selling_points = json.loads(scenario.core_selling_points)
    topics = json.loads(scenario.discussion_topics)

    records = ConversationRecord.query.filter_by(scenario_id=id).order_by(ConversationRecord.timestamp).all()
    conversation_history = []
    for r in records[-10:]:
        if r.is_host:
            conversation_history.append({"participant": "主持人", "content": r.content})
        elif r.participant_id == -1:
            conversation_history.append({"participant": "我", "content": r.content})
        else:
            participant = next((p for p in participants if p.id == r.participant_id), None)
            if participant:
                conversation_history.append({"participant": participant.persona_name, "content": r.content})

    import random
    num_responses = min(random.randint(1, 3), len(participants))
    selected_participants = random.sample(participants, num_responses)

    for participant in selected_participants:
        history_text = "\n".join([f"{h['participant']}：{h['content']}" for h in conversation_history[-8:]])
        interaction_types = ["回应", "赞同", "补充", "提问", "建议"]
        interaction_type = random.choice(interaction_types)

        prompt = f"""你"{participant.persona_name}"正在参加一个关于产品的讨论会，刚才有个用户发表了自己的看法。

你的身份背景：{participant.persona_name}，{participant.background}
你的性格特点：{participant.personality}
你的标签：{','.join(json.loads(participant.persona_tags))}

我们今天讨论的产品是「{scenario.product_name}」：
- 产品概念：{scenario.product_concept}
- 核心卖点：{','.join(selling_points)}

之前的讨论：
{history_text}

用户刚才说："{content}"

听到用户的话后，你作为"{participant.persona_name}"想回应一下。你可以说：
- 对用户观点的认同或补充
- 结合自己经历的一些想法
- 提出一个相关的问题

请用口语化的方式自然地回应，60-150字，不用太长。"""

        system_prompt = "你是一个真实的消费者，说话有自己的风格。不会刻意迎合，但也不会无礼。会因为同意而认可，也会因为不同意见而表达疑虑。"

        response = call_deepseek(prompt, system_prompt)

        if response.startswith(("API Error", "Request Error", "请求失败")):
            response = random.choice([
                f"{participant.persona_name}点头表示赞同：\"嗯，你说得有道理。\"",
                f"{participant.persona_name}若有所思地说：\"这个观点很有意思...\"",
                f"{participant.persona_name}：\"我也有类似的看法。\""
            ])
            print(f"AI请求失败，使用备用回复: {response}")

        ai_record = ConversationRecord(
            scenario_id=id,
            participant_id=participant.id,
            content=response,
            is_host=False,
            message_type='normal'
        )
        db.session.add(ai_record)
        db.session.commit()

        conversation_history.append({"participant": participant.persona_name, "content": response})

    return app.response_class(
        response=json.dumps({"status": "success", "message": "消息已添加", "ai_responses": num_responses}, ensure_ascii=False),
        status=200,
        mimetype='application/json; charset=utf-8'
    )

@app.route('/api/scenarios/<int:id>/generate-report', methods=['POST'])
def generate_report_with_ai(id):
    scenario, error_response = get_scenario_or_403(id)
    if error_response:
        return error_response
    
    records = ConversationRecord.query.filter_by(scenario_id=id).order_by(ConversationRecord.timestamp).all()

    if not records:
        return app.response_class(
            response=json.dumps({"error": "请先进行对话模拟"}, ensure_ascii=False),
            status=400,
            mimetype='application/json; charset=utf-8'
        )

    participants = VirtualParticipant.query.filter_by(scenario_id=id).all()

    conversation_lines = []
    for r in records:
        if r.is_host:
            participant_name = "主持人"
        elif r.participant_id == -1:
            participant_name = "用户"
        else:
            participant = next((p for p in participants if p.id == r.participant_id), None)
            participant_name = participant.persona_name if participant else "未知"
        conversation_lines.append(f"{participant_name}：{r.content}")
    
    conversation_text = "\n".join(conversation_lines)

    current_date = datetime.now().strftime("%Y年%m月%d日")

    prompt = f"""请根据以下焦点小组讨论内容，生成一份专业的市场分析报告。

产品信息：
产品名称：{scenario.product_name}
产品概念：{scenario.product_concept}
核心卖点：{','.join(json.loads(scenario.core_selling_points))}

讨论内容：
{conversation_text}

请生成一份结构清晰、内容详实的分析报告，包括：
1. 报告标题（格式：产品名称-市场分析报告-日期）
2. 用户需求洞察
3. 产品优劣势分析
4. 市场定位建议
5. 总结与建议

要求：
1. 在报告正文开始处添加标记：=====REPORT_START=====
2. 在报告正文结束处添加标记：=====REPORT_END=====
3. 只输出报告内容，不要添加额外的开场白或结束语

直接输出完整的报告内容，使用中文。"""

    system_prompt = "你是一位经验丰富的产品顾问，擅长从用户讨论中提炼有价值的产品洞察和商业建议。"

    result = call_deepseek(prompt, system_prompt)

    report_title = f"{scenario.product_name} - 产品分析报告 ({current_date})"
    
    start_marker = "=====REPORT_START====="
    end_marker = "=====REPORT_END====="
    
    start_idx = result.find(start_marker)
    end_idx = result.find(end_marker)
    
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        report_content = result[start_idx + len(start_marker):end_idx].strip()
    elif start_idx != -1:
        report_content = result[start_idx + len(start_marker):].strip()
    else:
        report_content = result.strip()

    existing_report = AnalysisReport.query.filter_by(scenario_id=id).first()
    if existing_report:
        existing_report.report_title = report_title
        existing_report.content = report_content
        existing_report.generated_at = datetime.now()
        db.session.commit()
        report = existing_report
    else:
        report = AnalysisReport(
            scenario_id=id,
            report_title=report_title,
            content=report_content
        )
        db.session.add(report)
        db.session.commit()

    return app.response_class(
        response=json.dumps(report.to_dict(), ensure_ascii=False),
        status=200,
        mimetype='application/json; charset=utf-8'
    )

@app.route('/api/scenarios/<int:id>/report', methods=['GET'])
def get_scenario_report(id):
    _, error_response = get_scenario_or_403(id)
    if error_response:
        return error_response
    
    report = AnalysisReport.query.filter_by(scenario_id=id).first()
    if not report:
        return app.response_class(
            response=json.dumps({"error": "暂无报告，请先生成"}, ensure_ascii=False),
            status=404,
            mimetype='application/json; charset=utf-8'
        )
    return app.response_class(
        response=json.dumps(report.to_dict(), ensure_ascii=False),
        status=200,
        mimetype='application/json; charset=utf-8'
    )

@app.route('/api/reports/<int:id>', methods=['GET'])
def get_report(id):
    report = AnalysisReport.query.get_or_404(id)
    return app.response_class(
        response=json.dumps(report.to_dict(), ensure_ascii=False),
        status=200,
        mimetype='application/json; charset=utf-8'
    )

@app.route('/api/scenarios/<int:id>/report/pdf', methods=['GET'])
def get_report_pdf(id):
    _, error_response = get_scenario_or_403(id)
    if error_response:
        return error_response
    
    report = AnalysisReport.query.filter_by(scenario_id=id).first()
    if not report:
        return app.response_class(
            response=json.dumps({"error": "暂无报告，请先生成"}, ensure_ascii=False),
            status=404,
            mimetype='application/json; charset=utf-8'
        )

    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.units import inch
    from reportlab.lib.enums import TA_CENTER

    result = BytesIO()
    doc = SimpleDocTemplate(result, pagesize=A4)
    styles = getSampleStyleSheet()
    
    try:
        if platform.system() == 'Windows':
            font_paths = [
                ('MicrosoftYaHei', 'C:\\Windows\\Fonts\\msyh.ttc'),
                ('SimSun', 'C:\\Windows\\Fonts\\simsun.ttc'),
                ('SimHei', 'C:\\Windows\\Fonts\\simhei.ttf')
            ]
            font_name = None
            for name, path in font_paths:
                if os.path.exists(path):
                    try:
                        pdfmetrics.registerFont(TTFont(name, path))
                        font_name = name
                        break
                    except:
                        continue
        else:
            font_name = 'Helvetica'
    except:
        font_name = 'Helvetica'
    
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontName=font_name,
        fontSize=18,
        alignment=TA_CENTER,
        spaceAfter=30
    )
    
    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontName=font_name,
        fontSize=11,
        leading=18
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontName=font_name,
        fontSize=14,
        spaceBefore=15,
        spaceAfter=8
    )
    
    story = []
    
    story.append(Paragraph(report.report_title, title_style))
    
    meta_text = f"报告生成时间：{report.generated_at.strftime('%Y年%m月%d日 %H:%M:%S')}"
    meta_style = ParagraphStyle(
        'MetaStyle',
        parent=styles['Normal'],
        fontName=font_name,
        fontSize=10,
        textColor='#666666',
        alignment=TA_CENTER
    )
    story.append(Paragraph(meta_text, meta_style))
    story.append(Spacer(1, 20))
    
    lines = report.content.split('\n')
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith('# '):
            story.append(Paragraph(line[2:], heading_style))
        elif line.startswith('## '):
            story.append(Paragraph(line[3:], heading_style))
        elif line.startswith('### '):
            story.append(Paragraph(line[4:], heading_style))
        elif line.startswith('- ') or line.startswith('* '):
            story.append(Paragraph('• ' + line[2:], normal_style))
        elif line.startswith('**') and line.endswith('**'):
            story.append(Paragraph(f'<b>{line[2:-2]}</b>', normal_style))
        else:
            story.append(Paragraph(line, normal_style))
        story.append(Spacer(1, 6))
    
    story.append(Spacer(1, 30))
    footer_style = ParagraphStyle(
        'FooterStyle',
        parent=styles['Normal'],
        fontName=font_name,
        fontSize=9,
        textColor='#999999',
        alignment=TA_CENTER
    )
    story.append(Paragraph('焦点小组讨论系统 - 分析报告', footer_style))
    
    doc.build(story)
    pdf_bytes = result.getvalue()

    response = make_response(pdf_bytes)
    response.headers['Content-Type'] = 'application/pdf'
    filename = f"analysis_report_{datetime.now().strftime('%Y%m%d')}.pdf"
    response.headers['Content-Disposition'] = f'attachment; filename="{quote(filename)}"'
    
    return response

def format_report_content(content):
    if not content:
        return '<p>报告内容为空</p>'
    
    import re
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', content)
    
    lines = text.split('\n')
    result = []
    in_table = False
    table_rows = []
    
    for line in lines:
        line = line.strip()
        if not line:
            if in_table:
                result.append('</tbody></table>')
                result.append('<br>')
                in_table = False
                table_rows = []
            continue
        
        heading_match = re.match(r'^(#{1,6})\s+(.+)$', line)
        if heading_match:
            if in_table:
                result.append('</tbody></table>')
                result.append('<br>')
                in_table = False
                table_rows = []
            level = len(heading_match.group(1))
            result.append(f'<h{level}>{heading_match.group(2)}</h{level}>')
            continue
        
        if re.match(r'^\|.+\|$', line):
            cells = [c.strip() for c in line.split('|') if c.strip() and not re.match(r'^-+$', c)]
            if len(cells) > 0:
                if not in_table:
                    in_table = True
                    table_rows = []
                    result.append('<table class="report-table">')
                
                is_separator = re.match(r'^\|[-:\s]+\|[-:\s]+\|$', line)
                if is_separator:
                    continue
                
                table_rows.append(cells)
                
                if len(table_rows) == 1:
                    result.append('<thead><tr>')
                    for cell in cells:
                        result.append(f'<th>{cell}</th>')
                    result.append('</tr></thead><tbody>')
                else:
                    result.append('<tr>')
                    for cell in cells:
                        result.append(f'<td>{cell}</td>')
                    result.append('</tr>')
            continue
        else:
            if in_table:
                result.append('</tbody></table>')
                result.append('<br>')
                in_table = False
                table_rows = []
        
        if line.startswith('- ') or line.startswith('* '):
            result.append(f'<li>{line[2:]}</li>')
        elif line == '---':
            result.append('<hr>')
        else:
            result.append(f'<p>{line}</p>')
    
    if in_table:
        result.append('</tbody></table>')
    
    html = '\n'.join(result)
    
    if '<thead><tbody>' in html:
        html = html.replace('<thead><tbody>', '<thead></thead><tbody>')
    if html.endswith('</tbody></table>'):
        html = html.replace('<table class="report-table"></thead></tbody></table>', '<table class="report-table"></table>')
    
    return html

@app.route('/api/participants', methods=['GET'])
def get_participants():
    participants = VirtualParticipant.query.all()
    return app.response_class(
        response=json.dumps([p.to_dict() for p in participants], ensure_ascii=False),
        status=200,
        mimetype='application/json; charset=utf-8'
    )

@app.route('/api/scenarios/<int:id>/participants', methods=['GET'])
def get_scenario_participants(id):
    participants = VirtualParticipant.query.filter_by(scenario_id=id).all()
    return app.response_class(
        response=json.dumps([p.to_dict() for p in participants], ensure_ascii=False),
        status=200,
        mimetype='application/json; charset=utf-8'
    )

@app.route('/api/participants/<int:id>', methods=['DELETE'])
def delete_participant(id):
    participant = VirtualParticipant.query.get_or_404(id)
    scenario_id = participant.scenario_id
    db.session.delete(participant)
    db.session.commit()
    return app.response_class(
        response=json.dumps({"status": "success", "message": f"参与者 {id} 已删除", "scenario_id": scenario_id}, ensure_ascii=False),
        status=200,
        mimetype='application/json; charset=utf-8'
    )

@app.route('/api/scenarios/<int:id>', methods=['DELETE'])
def delete_scenario(id):
    scenario, error_response = get_scenario_or_403(id)
    if error_response:
        return error_response

    ConversationRecord.query.filter_by(scenario_id=id).delete()
    VirtualParticipant.query.filter_by(scenario_id=id).delete()
    AnalysisReport.query.filter_by(scenario_id=id).delete()
    db.session.delete(scenario)
    db.session.commit()

    return app.response_class(
        response=json.dumps({"status": "deleted", "message": f"场景 {id} 已删除"}, ensure_ascii=False),
        status=200,
        mimetype='application/json; charset=utf-8'
    )

@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password', '')

    if not username or not email or not password:
        return app.response_class(
            response=json.dumps({"error": "用户名、邮箱和密码都不能为空"}, ensure_ascii=False),
            status=400,
            mimetype='application/json; charset=utf-8'
        )

    if User.query.filter_by(username=username).first():
        return app.response_class(
            response=json.dumps({"error": "用户名已存在"}, ensure_ascii=False),
            status=400,
            mimetype='application/json; charset=utf-8'
        )

    if User.query.filter_by(email=email).first():
        return app.response_class(
            response=json.dumps({"error": "邮箱已被注册"}, ensure_ascii=False),
            status=400,
            mimetype='application/json; charset=utf-8'
        )

    password_hash = hashlib.sha256(password.encode()).hexdigest()

    user = User(
        username=username,
        email=email,
        password_hash=password_hash
    )
    db.session.add(user)
    db.session.commit()

    session['user_id'] = user.id
    session['username'] = user.username

    return app.response_class(
        response=json.dumps({"status": "success", "user": user.to_dict()}, ensure_ascii=False),
        status=201,
        mimetype='application/json; charset=utf-8'
    )

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()

    if not username or not password:
        return app.response_class(
            response=json.dumps({"error": "用户名或密码错误"}, ensure_ascii=False),
            status=401,
            mimetype='application/json; charset=utf-8'
        )

    password_hash = hashlib.sha256(password.encode()).hexdigest()
    user = User.query.filter_by(username=username, password_hash=password_hash).first()

    if not user:
        return app.response_class(
            response=json.dumps({"error": "用户名或密码错误"}, ensure_ascii=False),
            status=401,
            mimetype='application/json; charset=utf-8'
        )

    session['user_id'] = user.id
    session['username'] = user.username

    return app.response_class(
        response=json.dumps({"status": "success", "user": user.to_dict()}, ensure_ascii=False),
        status=200,
        mimetype='application/json; charset=utf-8'
    )

@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return app.response_class(
        response=json.dumps({"message": "已退出登录"}, ensure_ascii=False),
        status=200,
        mimetype='application/json; charset=utf-8'
    )

@app.route('/api/user', methods=['GET'])
def get_user():
    user_id = session.get('user_id')
    if not user_id:
        return app.response_class(
            response=json.dumps({"error": "未登录"}, ensure_ascii=False),
            status=401,
            mimetype='application/json; charset=utf-8'
        )

    user = User.query.get(user_id)
    if not user:
        return app.response_class(
            response=json.dumps({"error": "无效的登录状态"}, ensure_ascii=False),
            status=401,
            mimetype='application/json; charset=utf-8'
        )

    return app.response_class(
        response=json.dumps(user.to_dict(), ensure_ascii=False),
        status=200,
        mimetype='application/json; charset=utf-8'
    )

@app.route('/api/current-user', methods=['GET'])
def get_current_user():
    user_id = session.get('user_id')
    if not user_id:
        return app.response_class(
            response=json.dumps({"error": "未登录"}, ensure_ascii=False),
            status=401,
            mimetype='application/json; charset=utf-8'
        )

    user = User.query.get(user_id)
    if not user:
        return app.response_class(
            response=json.dumps({"error": "无效的登录状态"}, ensure_ascii=False),
            status=401,
            mimetype='application/json; charset=utf-8'
        )

    return app.response_class(
        response=json.dumps(user.to_dict(), ensure_ascii=False),
        status=200,
        mimetype='application/json; charset=utf-8'
    )

@app.route('/api/occasion-types', methods=['GET'])
def get_occasion_types():
    return app.response_class(
        response=json.dumps([
            {"value": "focus_group", "label": "焦点小组讨论"},
            {"value": "user_interview", "label": "用户深度访谈"},
            {"value": "brainstorming", "label": "头脑风暴会议"},
            {"value": "product_team", "label": "产品团队评审"},
            {"value": "sales_conversation", "label": "销售对话模拟"}
        ], ensure_ascii=False),
        status=200,
        mimetype='application/json; charset=utf-8'
    )

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=5000)