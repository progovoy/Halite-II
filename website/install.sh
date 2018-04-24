#!/bin/bash

bundle install --path=vendor/bundle
npm install
cd ../libhaliteviz
npm install
cd ../website
npm run build
