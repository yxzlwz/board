import json
import os
import random
import time

from flask import *
import flask_cors
import lightmysql

import config

app = Flask(__name__)  # 初始化app对象
flask_cors.CORS(app, supports_credentials=True)
app.secret_key = "yxzlchatbox"  # session的加密密钥
thisDir = os.path.dirname(__file__)  # 相对目录
mysql = lightmysql.Connect(config.m_host,
                           config.m_user,
                           config.m_password,
                           config.m_database,
                           port=config.m_port,
                           pool_size=2)
maxLen = 250
rooms = {}
private_rooms = {}
_ = mysql.select("rooms", ["room", "type", "members", "owner", "token"])
for i in _:
    rooms[i[0]] = i[1]
    if i[1] == "private":
        private_rooms[i[0]] = {
            "members": i[2].split(","),
            "owner": i[3],
            "token": i[4]
        }


def generate_random_str(random_length=16):
    random_str = ""
    for i in range(random_length):
        random_str += random.choice(
            "ABCDEFGHIGKLMNOPQRSTUVWXYZabcdefghigklmnopqrstuvwxyz0123456789")
    return random_str


def decode_string(text):
    if not text:
        return text
    text = text.split("-")
    ans = ""
    for i in text:
        ans = ans + chr(int(i) - 99)
    return ans


def info_init():
    if request.cookies.get("username"):
        session["username"] = decode_string(request.cookies["username"])
    else:
        session["username"] = ""
    session[
        "private"] = f"匿名用户|{str(hash(request.headers.get('Ali-CDN-Real-IP')) % 10000).zfill(4)}"


@app.route("/api", methods=["GET", "POST"])
def api():
    global rooms, private_rooms
    result = {}
    try:
        name = request.values["room"].lower()
        token = request.values.get("token")
        pieces = request.values.get("pieces") or maxLen
    except KeyError:
        result = {"status": "fail", "description": "缺少参数", "data": []}
        return json.dumps(result, ensure_ascii=False), {
            "Content-Type": "application/json"
        }
    if name not in rooms.keys():
        result = {
            "status": "fail",
            "description": "找不到对应的房间（若room类型为public，请保证房间中至少有一条信息）",
            "data": []
        }
    elif rooms[name] == "private" and private_rooms[name]["token"] != token:
        result = {"status": "fail", "description": "token错误", "data": []}
    else:
        try:
            pieces = min(maxLen, int(pieces))
            data = mysql.select("messages", ["user", "content", "time"],
                                {"room": name})
            if len(data) > maxLen:
                data = data[-pieces:]
            result = {"status": "success", "description": "成功", "data": []}
            data = data[::-1]
            for i in data:
                result["data"].append({
                    "user": i[0],
                    "content": i[1],
                    "time": i[2]
                })
        except ValueError:
            result = {
                "status": "fail",
                "description": "pieces参数不是int格式",
                "data": []
            }
    return json.dumps(result, ensure_ascii=False), {
        "Content-Type": "application/json"
    }


@app.route("/<name>", methods=["GET", "POST"])
def board(name):
    global rooms, private_rooms
    info_init()
    name = name.lower()
    if rooms.get(name) and rooms[name] == "private" and session[
            "username"] not in private_rooms[name]["members"]:
        return "错误：您无权访问该private房间！", 403
    if request.method == "POST":
        if request.form.get("text"):
            if request.form["send_type"] == "public" or rooms.get(
                    name) == "private":
                user = session["username"]
            else:
                user = session["private"]
            if name not in rooms.keys():
                mysql.insert("rooms", {"room": name, "type": "public"})
                rooms[name] = "public"
            mysql.insert(
                "messages", {
                    "room": name,
                    "user": user,
                    "content": request.form["text"].replace("\r\n", "\n"),
                    "time": round(time.time() * 1000)
                })

        return "Success"
    else:
        data = mysql.select("messages", ["user", "content", "time"],
                            {"room": name})
        if len(data) > maxLen:
            data = data[-maxLen:]
        for i in range(len(data)):
            data[i] = list(data[i])
            data[i][1] = data[i][1].split("\n")
            for j in range(len(data[i][1])):
                data[i][1][j] = data[i][1][j].split("\t")
        token = rooms.get(
            name) == "private" and private_rooms[name]["token"] or ""
        return render_template("board.html",
                               name=name,
                               chat=data[::-1],
                               username=session["username"],
                               token=token,
                               private=session["private"],
                               room_type=rooms.get(name))


@app.route("/", methods=["GET", "POST"])
def index():
    global rooms, private_rooms
    info_init()
    if request.method == "POST":
        name = request.form["name"].lower()
        members = session["username"] + "," + request.form["member"]
        if not session["username"]:
            return "操作失败：您还未登录！"
        if name in rooms.keys():
            if rooms[name] == "public":
                return "操作失败：该房间已作为公共房间使用，无法设置私有。"
            while members[-1] == ",":
                members = members[:-1]
            if private_rooms[name]["owner"] != session["username"]:
                return "操作失败：该房间已存在且不属于您！"
            mysql.update("rooms", {"members": members}, {"room": name})
            private_rooms[name]["members"] = members.split(",")
            return "Success"
        token = generate_random_str(8)
        mysql.insert(
            "rooms", {
                "room": name,
                "type": "private",
                "members": members,
                "owner": session["username"],
                "token": token
            })
        rooms[name] = "private"
        private_rooms[name] = {
            "members": members.split(","),
            "owner": session["username"],
            "token": token
        }
        return "Success"
    return render_template("index.html",
                           username=session["username"],
                           private=session["private"])


@app.errorhandler(404)
def error_404(message):
    return redirect("/")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8088, debug=True)
