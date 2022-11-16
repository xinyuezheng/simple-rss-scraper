# A simple RSS scraper application which saves RSS feeds to a database and lets a user view and manage feeds

## Overall Architecture  
Django Rest Framework. Celery+Redis are used for processing the heavy tasks asynchronously  
There are 2 message queues set up in the system. Queue 'force_feed_update' is dedicated for user manually updates a feed. The 'default' celery queue is used by the 'celery-beat' to periodically update feeds at background. There are 2 celery workers spun up from 'docker-compose.yml' file. One worker listens only to the 'force_feed_update' queue. So the user update requests can be processed independently with the background feeds update. The other worker listens to both queues.  


## HowTo Start  
1. Go to the root folder 'sendcloud_test',
2. Build a docker image: `docker build -t rssscraper .`
3. Run docker-compose: `docker-compose up -d`
4. Create a user: send POST request to http://127.0.0.1:8000/user/registration/ with username, password, email. email is required, to notify user if feed fails to update   `curl -d "username=string&password=string&email=user@example.com" http://127.0.0.1:8000/user/registration/`
5. The system accepts both token authentication and session authentication (browsable api friendly). For token authentication, send POST request to  http://127.0.0.1:8000/token/ with username and password to obtain access,refresh token pair.  `curl -d "username=string&password=string http://127.0.0.1:8000/token/" `
6. Requests to all other endpoints must be authenticated. For example, with access token  `curl http://127.0.0.1:8000/feed/ -H "Accept: application/json -H "Authorization: Bearer <access token>"`

## Environment variables
Environment variables are specified in the 'docker.env' file under the root path  
- `DAYS_RETRIEVABLE=7` How many days a user can retrieve his/her followed feed entries through the APIs  
- `MAXIMUM_RETRY=2` How many times to retry if an error happens during the feed update.  
- `UPDATE_INTERVAL=3600.0`  Interval (in seconds) 'celery-beat' periodically updates feeds at background  

## Docker Containers
There are 5 containers specified in docker-compose.yml file. 
1. web: processing user requests and response
2. celery_beat: schedule tasks to update feeds periodically at background
3. celery_worker_force_update: only process tasks sent by user to update a feed manually
4. celery_worker_default: process any task
5. redis: message queue broker
### docker volumes
All containers except for redis have 2 folders 'db' and 'logs' under the rootpath 'sendcloud_test' mounted as persistence storage 
- 'db' folder contains the database file 'db.sqlite3'
- 'logs' folder contains the log file 'rssfeed.log'  

There is an existing database file 'db.sqlite3' which I used to test the system. It has a setup of a few feeds followed by 2 users. There are a few thousands feed entries created over the last weeks. If you wish to start clean, replace it with a new by 'python manage.py migrate'. The existing users and passwords are 'xinyue:rssfeed' and 'user2:user2'. 'xinyue' is a superuser.

## Documentation
Once the system is up and running, the API details can be found at
- http://127.0.0.1:8000/swagger/ 
- http://127.0.0.1:8000/redoc/ 
- http://127.0.0.1:8000/swagger.json (export to other tools such as Postman)

## Test
- pipenv dev environment is required to run tests. Run `pipenv install --dev` to install all required packages.  
- Go to site folder 'sendcloud_test/rssfeed', run `pytest .`


## Other known issues 
For demo purpose, the following components are chosen just for the sake of simplicity  
1. Django built-in 'runserver' instead of a production level webserver such as Nginx, Apache etc.
2. SQLite database instead of a production level database such as Postgres, SQLServer etc.
3. SendEmail feature is faked
4. Redis as a message broker instead of a dedicated message broker such as RabbitMQ which provides higher throughput, better security etc.
5. The system is assumed to be hosted locally on "127.0.0.1:8000" with 'http' protocol

'select_for_update' is used to avoid multiple workers update the feed status at the same time. However SQLite does not need 'select_for_update' because initiating a transaction locks the entire database. I put it here anyway to be compatible with other database such as Postgres, MySQL.
