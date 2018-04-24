#!/bin/bash

docker run --net=host -it -d -p 4000:4000 -v /home/ubuntu/Halite-II:/halite2/ halite_website
