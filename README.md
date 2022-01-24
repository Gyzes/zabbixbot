# ZabbixBot

**Run bot:**

Requirments: 
- Zabbix-server: >=5.4
- docker
- docker-compose

Create bot on @BotFather in Telegram

For start bot:
1) Download project

`git clone https://github.com/Gyzes/zabbixbot.git`

2) Change .env.sample and rename to ".env"

3) Start containers:

`docker-compose up -d`

**Configure HTTPS**
Generate self-signed certificate

`openssl req -x509 -newkey rsa:2048 -keyout key.pem -out ca.pem -days 1080 -nodes -subj '/CN=*/O=My Company Name LTD./C=US'`

`cp key.pem cert.pem`

`cat ca.pem >> cert.pem`

`awk 1 ORS='\\n' cert.pem`

**Configure notifications in Zabbix:**

1) Import media types from zbx_mediatypes.yaml and change value "URL"

   <img src="assets/add_media_type.jpg" alt="add media type"/>

2) In user media type set Telegram id

   <img src="assets/user_media_type.jpg" alt="add media type"/>
3) Configure Action for send notification

For disable send graph for trigger set tag: graph with value "False"

**Examples**

1) Autoregistration

<img src="assets/autoregistration.jpg" alt="autoregitration">

2) Trigger

<img src="assets/trigger.jpg" alt="trigger">

3) Ping

<img src="assets/ping.jpg" alt="ping">
