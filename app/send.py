import telebot
from telebot import types
from flask import Flask, request, abort
from redis import Redis
import os
import socket
import requests
import json
import sys


def print_message(string):
    string = str(string) + "\n"
    filename = sys.argv[0].split("/")[-1]
    sys.stderr.write(filename + ": " + string)


class ZabbixWeb:
    def __init__(self, server, username, password):
        self.debug = False
        self.server = server
        self.username = username
        self.password = password
        self.proxies = {}
        self.verify = True
        self.cookie = None
        self.basic_auth_user = None
        self.basic_auth_pass = None
        self.tmp_dir = None

    def login(self):
        if not self.verify:
            requests.packages.urllib3.disable_warnings()

        data_api = {"name": self.username, "password": self.password, "enter": "Sign in"}
        answer = requests.post(self.server + "/", data=data_api, proxies=self.proxies, verify=self.verify,
                               auth=requests.auth.HTTPBasicAuth(self.basic_auth_user, self.basic_auth_pass))
        cookie = answer.cookies
        if len(answer.history) > 1 and answer.history[0].status_code == 302:
            print_message("probably the server in your config file has not full URL (for example "
                          "'{0}' instead of '{1}')".format(self.server, self.server + "/zabbix"))
        if not cookie:
            print_message("authorization has failed, url: {0}".format(self.server + "/"))
            cookie = None

        self.cookie = cookie

    def graph_get(self, itemid, period, title, width, height, version=3):
        title = requests.utils.quote(title)

        colors = {
            0: "00CC00",
            1: "CC0000",
            2: "0000CC",
            3: "CCCC00",
            4: "00CCCC",
            5: "CC00CC",
        }

        drawtype = 5
        if len(itemid) > 1:
            drawtype = 2

        zbx_img_url_itemids = []
        for i in range(0, len(itemid)):
            itemid_url = "&items[{0}][itemid]={1}&items[{0}][sortorder]={0}&" \
                         "items[{0}][drawtype]={3}&items[{0}][color]={2}".format(i, itemid[i], colors[i], drawtype)
            zbx_img_url_itemids.append(itemid_url)

        zbx_img_url = self.server + "/chart3.php?"
        if version < 4:
            zbx_img_url += "period={0}".format(period)
        else:
            zbx_img_url += "from=now-{0}&to=now".format(period)
        zbx_img_url += "&name={0}&width={1}&height={2}&graphtype=0&legend=1".format(title, width, height)
        zbx_img_url += "".join(zbx_img_url_itemids)

        answer = requests.get(zbx_img_url, cookies=self.cookie, proxies=self.proxies, verify=self.verify,
                              auth=requests.auth.HTTPBasicAuth(self.basic_auth_user, self.basic_auth_pass))
        status_code = answer.status_code
        if status_code == 404:
            print_message("can't get image from '{0}'".format(zbx_img_url))
            return False
        return answer.content


def get_graph(data):
    try:
        image = redis.get(data['graph']['triggerid'])
    except KeyError:
        image = None
    if image:
        app.logger.info('image in cache')
        return image
    else:
        image = zbx.graph_get(
            data['graph']['itemid'],
            data['graph']['period'],
            data['message']['title'],
            900,
            200,
            version=int(os.getenv('zbx_server_version'))
        )
        try:
            redis.set(data['graph']['triggerid'], image, 60)
        except KeyError:
            pass
        return image


emoji_map = {
    "OK": "✅",
    "PROBLEM": "❗",
    "info": "ℹ️",
    "Information": "ℹ️",
    "Warning": "⚠️",
    "Disaster": "❌",
    "High": "💣",
    "Average": "🔥",
    "hankey": "💩",
}


def replace_emoji(text):
    for k, v in list(emoji_map.items()):
        text = text.replace("{{" + k + "}}", v)
    return text


def create_keyboard_list(itemid):
    keyboard = types.InlineKeyboardMarkup(row_width=5)
    reply_markup = [("1h", "3600;" + itemid),
                    ("3h", "10800;" + itemid),
                    ("6h", "21600;" + itemid),
                    ("12h", "43200;" + itemid),
                    ("24h", "86400;" + itemid)]
    buttons = [types.InlineKeyboardButton(text=i, callback_data=k) for i, k in reply_markup]
    keyboard.add(*buttons)
    return keyboard


zbx = ZabbixWeb(server=os.getenv('zbx_server'), username=os.getenv('zbx_api_user'),
                password=os.getenv('zbx_api_pass'))
zbx.login()
redis_pass = os.getenv('REDIS_PASSWORD', '')
redis = Redis(host='redis', port=6379, db=0, password=redis_pass)
app = Flask(__name__)
host = socket.gethostname()
bot = telebot.TeleBot(os.getenv('TG_TOKEN'))


@app.before_request
def limit_remote_addr():
    try:
        if request.headers['X-Real-Ip'] not in os.getenv('whitelist_ip') and \
                request.headers['Authorization'] != os.getenv('authorization_token'):
            app.logger.info('Forbidden POST request: ' + request.headers['X-Real-Ip'])
            abort(403)  # Forbidden
    except KeyError:
        abort(403)


@app.route('/', methods=['POST'])
def get_data_post():
    data = request.get_json()
    if os.getenv('DEBUG', 'False') == 'True':
        app.logger.info(data)

    try:
        if data['graph'] and not data['graph']['itemid'] == ["{ITEM.ID}"]:
            graph = True
        else:
            graph = False
    except KeyError:
        graph = False

    try:
        user = data['to']
        status = replace_emoji(data['message']['status'])
        title = data['message']['title']
        text = replace_emoji(data['message']['text'])
    except KeyError as err:
        app.logger.error(err.args[0] + ' in ' + str(data))
        return json.dumps({'success': False, 'error': 'KeyError: ' + err.args[0]}), 422, {
            'ContentType': 'application/json'}

    if graph:
        graph_image = get_graph(data)
        if not graph_image:
            app.logger.error('Fail get graph image')
            graph = False
        try:
            if data['graph']['buttons'] == 'True':
                reply_markup = create_keyboard_list(data['graph']['itemid'][0])
            else:
                reply_markup = None
        except KeyError:
            reply_markup = None

    try:
        message = bot.send_message(user, status + ' ' + title + '\n' + text)
    except Exception as err:
        error = 'Message error! Error: ' + err.args[0]
        app.logger.error(error)
        app.logger.info(data)
        return json.dumps({'success': False, 'error': error}), 504, {
            'ContentType': 'application/json'}
    if graph:
        try:
            bot.send_photo(user, graph_image, reply_to_message_id=message.message_id, reply_markup=reply_markup)
        except Exception as err:
            error = 'Photo error! Error: ' + err.args[0]
            app.logger.error(error)
            app.logger.info(data)
            return json.dumps({'success': False, 'error': error}), 504, {
                'ContentType': 'application/json'}

    return json.dumps({'success': True}), 200, {'ContentType': 'application/json'}


if __name__ == "__main__":
    if os.getenv('DEBUG') == 'True':
        debug = True
    else:
        debug = False
    app.run(host="0.0.0.0", port=80, debug=debug)
