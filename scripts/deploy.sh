#!/usr/bin/env bash

set -e

cd /home/anas/apps/mafia

echo "Pulling latest code..."
git pull origin main

echo "Building and starting containers..."
docker compose up -d --build

echo "Running Django migrations..."
docker compose exec -T app python manage.py migrate
