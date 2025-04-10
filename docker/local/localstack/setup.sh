#!/bin/sh

# create the bucket
awslocal s3 mb s3://itgdbtest

# set cors config for development
awslocal s3api put-bucket-cors --bucket itgdbtest --cors-configuration file:///cors-config.json