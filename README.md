# A simple RSS scraper application which saves RSS feeds to a database and lets a user view and manage feeds

## Overall Architecture  
Django Rest Framework. Celery+Redis are used for processing the heavy tasks asynchronously  
There are 2 message queues set up in the system. Queue 'force_feed_update' is dedicated for updating a feed manually from a user.
The 'default' celery queue is used by the 'celery-beat' to periodically update feeds at background.
There are 2 celery workers defined in the 'docker-compose.yml' file. One worker listens only to the 'force_feed_update' queue. Therefore,
a user's request to update a feed can be processed independently with other feeds update at background.

## HowTo Start  
1. Go to the root folder 'sendcloud_test',
2. Build a docker image: `docker build -t rssscraper .`
3. Run docker-compose: `docker-compose up -d`
4. Create a user: send POST request to http://127.0.0.1:8000/user/registration/ with username, password and email.
 run `curl -d "username=string&password=string&email=user@example.com" http://127.0.0.1:8000/user/registration/`
5. The system accepts both token authentication and session authentication (browsable api friendly). 
For token authentication, send POST request to  http://127.0.0.1:8000/token/ with username and password to obtain access,refresh token pair.  `curl -d "username=string&password=string http://127.0.0.1:8000/token/" `
6. Requests to all other endpoints must be authenticated. By using access token, run
`curl http://127.0.0.1:8000/feed/ -H "Accept: application/json -H "Authorization: Bearer <access token>"`

## Environment variables
Environment variables are specified in the 'docker.env' file under the rootpath  
- `DAYS_RETRIEVABLE=7` defines in how many days a user can retrieve his/her followed feed entries through the APIs  
- `MAXIMUM_RETRY=2` defines how many times to retry if an error occurs during a feed update.  
- `UPDATE_INTERVAL=3600.0` defines interval (in seconds) 'celery-beat' applies to update feeds periodically at background  

## Docker Containers
There are 5 containers specified in the 'docker-compose.yml' file. 
1. web: process user request and response
2. celery_beat: schedule tasks to update feeds periodically at background
3. celery_worker_force_update: only process tasks sent by user to update a feed manually
4. celery_worker_default: process any task available in the queues
5. redis: message queue broker
### docker volumes
All containers except for redis have folders 'sendcloud_test/db' and 'sendcloud_test/logs' mounted as persistence storage 
- 'db' folder contains the database file 'db.sqlite3'
- 'logs' folder contains the log file 'rssfeed.log'  

There is an existing database file 'sendcloud_test/db/db.sqlite3' which I used to test the system. 
It has a setup of a few feeds followed by 2 users. A few thousands entries were created over the last weeks. 
If you wish to start from clean, replace it with a new database by running 'python manage.py migrate'. 
The existing 2 users and their passwords are 'xinyue:rssfeed', 'user2:user2'. 'xinyue' is a superuser.

## Documentation
Once the system is up and running, the API details can be found at
- http://127.0.0.1:8000/swagger/ 
- http://127.0.0.1:8000/redoc/ 
- http://127.0.0.1:8000/swagger.json (export to other tools such as postman)

## Test
- pipenv dev environment is required to run tests. Run `pipenv install --dev` from the rootpath to install all required packages.  
- Go to the site folder 'sendcloud_test/rssfeed' and run `pytest .`


## Other known issues 
For demo purpose, the following components are chosen just for the sake of simplicity  
1. Django built-in 'runserver' instead of a production level webserver such as Nginx, Apache etc.
2. SQLite database instead of more powerful database such as Postgres, SQLServer etc.
3. SendEmail feature is faked
4. Use Redis as a message broker instead of a dedicated one such as RabbitMQ which provides higher throughput and better security.
5. The system is assumed to be hosted locally on "127.0.0.1:8000" with 'http' protocol, instead of 'https' with a domain name.

'select_for_update' is used to avoid multiple workers update the feed status at the same time.
However, SQLite does not need 'select_for_update' because initiating a transaction locks the entire database. 
I put it here anyway just to be compatible with other database such as Postgres, MySQL which supports multiple transactions running at
 the same time.
