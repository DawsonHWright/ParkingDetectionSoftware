#!/usr/bin/env bash

python detector.py \
    --source inputs \
    --mask outputs/masks/lot_mask.png \
    --post https://parkingdetectionsoftware.onrender.com/api/spots/update