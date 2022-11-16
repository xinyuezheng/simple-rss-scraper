# Aa simple RSS scraper application which saves RSS feeds to a database and lets a user view and manage feeds

## For demo purpose, the following components are chosen just for the sake of simplicity
1. Django built-in 'runserver' instead of a production level webserver such as Nginx, Apache etc.
2. SQLite database instead of a production level database such as Postgres, SQLServer etc.
3. SendEmail feature is faked
4. Redis as a message broker instead of a dedicated message broker such as RabbitMQ which provides higher throughput, better security etc.
5. The system is assumed to be hosted locally on "127.0.0.1:8000" with 'http' protocal


## Overall Architecture  
Django Rest Framework. Celery+Redis are used for processing the heavy tasks asynchronously  
There are 2 message queues set up in the system. Queue 'force_feed_update' is dedicated for user manually updates a feed. The 'default' celery queue is used by the 'celery-beat' to periodically update feeds at background. There are 2 celery workers spinned up from 'docker-compose.yml' file. One worker listens only to the 'force_feed_update' queue. So the user update requests can be processed independently ragarding the background feeds update. The other worker listens to both queues.  


## HowTo Start  
1. Go to the root folder 'sendcloud_test',
2. Build a docker image: `docker build -t rssscraper .`
3. Run docker-compose: `docker-compose up -d`
4. Create a user: send POST request to http://127.0.0.1:8000/user/registration/ with username, password, email. email is required, to notify user if feed fails to update   `curl -d "username=string&password=string&email=user@example.com" http://127.0.0.1:8000/user/registration/`
5. The system accepts both token authentication and session authentication (browserble api friendly). For token authentication, send POST request to  http://127.0.0.1:8000/token/ with username and password to obtain access,refresh token pair.  `curl -d "username=string&password=string http://127.0.0.1:8000/token/" `
6. Requests to all other endpoints must be authenticated. For example, with access token  `curl http://127.0.0.1:8000/feed/ -H "Accept: application/json -H "Authorization: Bearer <access token>"`

## Environment variables
Environment variables are specified in the 'docker.env' file under the root path  
- `DAYS_RETRIEVABLE=7` How many days a user can retrieve his/her followed feed entries through the APIs  
- `MAXIMUM_RETRY=2` How many times to retry if an error happens during the feed update.  
- `UPDATE_INTERVAL=3600.0`  Interval (in seconds) 'celery-beat' periodically updates feeds at background  

## Docker Volumes
- 'db' folder under the rootpath 'sendcloud_test' which contains the database file 'db.sqlite3' will be mounted to all containers, except for redis. 
- 'logs' folder under the rootpath 'sendcloud_test' which contains the log file 'rssfeed.log' will be mounted to all containers, except for redis.  

There is an existing database file 'db.sqlite3' which I used to test the system. It has a setup of a few feeds followed by 2 users. There are a few thousands feed entreis created over the last weeks. If you wish to start clean, replace it with a new by 'python manage.py migrate' 

## Documentation
Once the system is up and running, the API details can be found at
- http://127.0.0.1:8000/swagger/ 
- http://127.0.0.1:8000/redoc/ 
- http://127.0.0.1:8000/swagger.json (export to other tools such as Postman)
