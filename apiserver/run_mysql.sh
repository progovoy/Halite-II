#!/bin/bash

docker run --net=host --rm -d -v $(pwd)/../db:/var/lib/mysql -e MYSQL_ALLOW_EMPTY_PASSWORD=yes -p 3306:3306 halite_sql
