Aa simple RSS scraper application which saves RSS feeds to a database and lets a user view and manage feeds

For demo purpose, this project uses the following compoments for the sake of simplicity
1) Django built-in 'runserver' instead of a production level webserver such as Nginx, Apache etc.
2) SQLite database instead of a production level database such as Postgres, SQLServer etc.
3) SendEmail feature is faked
4) Redis as a message broker instead of a dedicated message broker such as RabbitMQ which provides higher throughput,  better security, persistence messages etc.
5) The system is assumed to be hosted locally on "127.0.0.1:8000" with 'http' protocal



Overall Architecture  
Django Rest Framework with Celery+Redis for asynchronous background tasks  
There are 2 message queues set up in the system. Queue 'force_feed_update' is dedicated for user updating a feed manually. The 'default' celery queue is used by 'celery-beat' to periodically update feeds at background. There are 2 celery workers spinned up from 'docker-compose.yml' file. One worker listens only to the 'force_feed_update' queue. So the user request can be processed relative fast. The other worker listens to both queue.  



To run this project, 
1) Go to the root folder 'sendcloud_test',
2) Build a docker image: docker build -t rssscraper .
3) Run docker-compose: docker-compose up -d
4) To start using the system, send POST request to http://127.0.0.1:8000/user/registration/ with username, password, email to create a user (email is required, to notify user if feed fails to update)
5) The system accepts both token authentication and session authentication (web browsable api friendly). For token authentication, send POST request to  http://127.0.0.1:8000/token/ with username and password to obtain access,refresh token pair.
6) Send requests with access token (Eg. curl http://127.0.0.1:8000/feed/ -H "Accept: application/json -H "Authorization: Bearer {access token}")

The environment variables are specified in the 'docker.env' file in the root folder  
DAYS_RETRIEVABLE=7  => This indicates how many days a user can retrieve the followed feed entries through the APIs  
MAXIMUM_RETRY=2 => This indicates how many times to retry if a feed fails to be updated.  
UPDATE_INTERVAL=3600.0  => This is the interval (in seconds) celery-beat uses to update a feed at background  

The details of APIs can be found at http://127.0.0.1:8000/swagger/ Or downloadable at http://127.0.0.1:8000/redoc/ once the docker containers are up.

