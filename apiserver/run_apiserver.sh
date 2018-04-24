#!/bin/bash

docker run --net=host -it -d -p 5000:5000 -v /home/ubuntu/Halite-II:/home/ubuntu/Halite-II/ halite_apiserver


