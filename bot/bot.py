import telebot
import datetime
from pyzabbix import ZabbixAPI
from pythonping import ping
import requests
import json
import os


class ZabbixApi:
    def __init__(self, server, user, password):
        self.api = ZabbixAPI(server)
        self.user = user
        self.password = password

    def login(self):
        self.api.login(self.user, self.password)

    def triggers_active(self):
        return self.api.trigger.get(output="extend", monitored=True, min_severity=3, filter={"value": 1},
                                    sortfield="priority", sortorder="DESC", selectHosts="extend")

    def item_get(self, itemid):
        return self.api.item.get(itemids=itemid)

    def valuemap_get(self, value, _id):
        if _id == "0":
            return value
        else:
            for i in self.api.valuemap.get(valuemapids=_id, selectMappings='extend')[0]['mappings']:
                if i['value'] == value:
                    return i['newvalue'] + ' (' + str(value) + ")"

    def units_get(self, itemid):
        return self.api.item.get(itemids=itemid)[0]['units']


def units_replace(units, value):
    if units == 'uptime' or units == 's':
        sec = datetime.timedelta(seconds=int(value))
        uptime = datetime.datetime(1, 1, 1) + sec
        res = ''
        if uptime.year - 1 > 0:
            res += str(uptime.year - 1) + 'y '
        if uptime.month - 1 > 0:
            res += str(uptime.month - 1) + 'm '
        if uptime.day - 1 > 0:
            res += str(uptime.day - 1) + 'd '
        res += str(uptime.hour).zfill(2) + ':' + str(uptime.minute).zfill(2) + ':' + str(uptime.second).zfill(2)
        return res
    if units == '°C' or units == '%' or units == 'C':
        return str(round(float(value), 2)) + " " + units
    if units == 'B':
        unit = {0: 'B', 1: 'KB', 2: 'MB', 3: 'GB', 4: 'TB'}
        temp = 0
        while int(value) // 1024 > 0:
            temp += 1
            value = int(value) / 1024
        return str(round(value, 2)) + " " + unit[temp]
    if units == 'mail':
        return str(units)
    return str(value) + " " + str(units) + "!!!"


def check_access(message):
    if message.chat.username in os.getenv('tg_whitelist_username'):
        return True
    else:
        bot.send_message(message.chat.id, """Hey, this is Zabbix bot. It's private bot. If you need help, you can use 
        google.com""")
        print(str(datetime.datetime.now()) + ' INFO: Unauthorized access: ID={} Username={} Message={}'.format(
            message.chat.id, message.chat.username, message.text))
        return False


zbxapi = ZabbixApi(os.getenv('zbx_server'), os.getenv('zbx_api_user'), os.getenv('zbx_api_pass'))
zbxapi.login()

commands = [
    "/triggers",
    "/ping hostname",
    "/help",
]

emoji = {"1": "ℹ️", "3": "🔥", "4": "💣", "5": "❌", }
bot = telebot.TeleBot(os.getenv('TG_TOKEN'))


@bot.message_handler(commands=['triggers'])
def handle_triggers(message):
    if check_access(message):
        triggers = zbxapi.triggers_active()
        reply_text = list()
        if triggers:
            for t in triggers:
                reply_text.append("{{{{{0}}}}} Host: {1}, Trigger: {2},\n".format(
                    t["priority"],
                    str(t["hosts"][0]["name"]),
                    str(t["description"]).replace("{HOST.NAME}", str(t["hosts"][0]["name"]))
                ))
            reply_text_emoji_support = []

            for row in reply_text:
                l_new = row
                for k, v in list(emoji.items()):
                    l_new = l_new.replace("{{" + k + "}}", v)
                reply_text_emoji_support.append(l_new)
            reply_text = reply_text_emoji_support
        else:
            reply_text.append("There are no triggers, have a nice day!")
        bot.send_message(message.chat.id, '\n'.join(reply_text))
        if len(reply_text) > 30:
            with open('stickers/vsrato.webp', 'rb') as s:
                bot.send_sticker(message.chat.id, s)


@bot.message_handler(commands=['ping'])
def handle_ping(message):
    if check_access(message):
        host = message.text[6::]
        if len(host.split('.')) == 1:
            host = host + '.' + os.getenv('domain_name')
        if host == '.' + os.getenv('domain_name'):
            bot.send_message(message.chat.id, 'Укажите адрес хоста:\n/ping hostname')
            return
        reply_text = list()
        if len(host.split(" ")) == 1 and "|" not in host and "&" not in host:
            try:
                reply = str(ping(host))
            except:
                reply = "Cannot resolve address " + host
            for i in reply.split("\\n"):
                reply_text.append(i)
        else:
            reply_text.append("Incorrect hostname or IP address")
        bot.send_message(message.chat.id, '\n'.join(reply_text))


@bot.callback_query_handler(func=lambda x: True)
def handle_callback(message):
    period, itemid = message.data.split(";")
    title = message.message.json['reply_to_message']['text'].split("\n")[0]
    value = zbxapi.item_get(itemid)
    # преобразование value map
    value = zbxapi.valuemap_get(value[0]['lastvalue'], value[0]['valuemapid'])
    # преобразование значений
    units = zbxapi.units_get(itemid)
    if units != "":
        value = units_replace(units, value)
    text = message.message.json['reply_to_message']['text'].split("\n")[1:]
    text[-1] = text[-1].split(':')[0] + ': ' + value
    text = '\n'.join(text)
    data = {"to": message.from_user.id, "graph": {"buttons": "True", "itemid": [itemid], "period": period},
            "message": {"status": title[0], "title": title[2:], "text": text}}
    headers = {'Content-type': 'application/json', 'Authorization': os.getenv('authorization_token')}
    # TODO change to variable
    requests.post('http://lb', data=json.dumps(data), headers=headers)


@bot.message_handler(commands=['start', 'help'])
def handle_help(message):
    if check_access(message):
        bot.send_message(message.chat.id, 'Available commands:\n' + '\t\n'.join(commands))


@bot.message_handler()
def handle_message(message):
    bot.send_message(message.chat.id, "I don't know this command")


bot.polling(none_stop=True)
