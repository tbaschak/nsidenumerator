#!/bin/bash

FILES=$(git diff --name-only HEAD)
for file in $FILES
do
    mypy --ignore-missing-imports $file || (echo "mypy failed on $file" ; exit 1)
done

