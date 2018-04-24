#!/bin/bash

docker run --rm -d -v $(pwd)/../db:/var/lib/mysql -e MYSQL_ALLOW_EMPTY_PASSWORD=yes -p 44330:3306 halite_sql
