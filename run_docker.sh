#!/bin/sh

set -ie

D1="--env-file .env --rm -it"
D2="-p5432:5432 -v`pwd`:`pwd`"

docker run --rm -it $D1 $D2 --name pg postgres
