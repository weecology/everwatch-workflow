#!/bin/bash

source /blue/ewhite/hpc_maintenance/githubdeploytoken.txt

# Capture the current date and time for the commit message
date=$(date '+%Y-%m-%d %H:%M:%S')

# Change directory to the everwatch-predictions
cd /blue/ewhite/everglades/everwatch-predictions || exit

# git reset --hard
# git checkout main
# git fetch origin main
# git reset --hard origin/main

# # Set up the user information for Weecology Deploy Bot
# git config user.email "weecologydeploy@weecology.org"
# git config user.name "Weecology Deploy Bot"

# # Check if the TEST_ENV environment variable is set, skip actual deployment if it is
# if [ -n "$TEST_ENV" ]; then
#     echo "TEST_ENV is set: $TEST_ENV"
#     git checkout -B dry-run
#     git reset --hard origin/main
#     echo "Test dry run: $date" >> README.md
#     git add -u
#     git commit -m "Weecology Deploy Bot: Dry run tests from HiperGator $date [ci skip]"
#     git push origin dry-run -f
#     exit 0
# fi

# # Copy the updated PredictedBirds.zip file to the repository
# cp /blue/ewhite/everglades/everwatch-workflow/App/Zooniverse/data/PredictedBirds.zip \
#    /blue/ewhite/everglades/everwatch-predictions/PredictedBirds.zip

# # Copy the updated PredictedBirds.csv file to the repository
# cp /blue/ewhite/everglades/everwatch-workflow/App/Zooniverse/data/PredictedBirds.csv \
#    /blue/ewhite/everglades/everwatch-predictions/PredictedBirds.csv

# # Stage the files, commit with a message including the current date, and push changes
# git add PredictedBirds.zip PredictedBirds.csv
# git commit -m "Weecology Deploy Bot $date"

# # Set up the deploy remote for the portal-forecasts repository
# git remote remove deploy
# git remote add deploy https://${GITHUBTOKEN}@github.com/weecology/everwatch-predictions.git

# # Push the changes to the deploy remote's main branch
# git push --quiet deploy main

# # Uncomment the following lines if you want to tag the release and push tags
# # git tag $date
# # git push --quiet deploy --tags
