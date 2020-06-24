for file in pet/*.asc
do
	filename=$(basename $file)
	gdalwarp -tr 0.01 0.01 -te -96.0 29.5 -94.9 30.1 $file /home/ZhiLi/CRESTHH/data/evap/${filename}.tif

done
