for file in pet/*.asc
do
	filename=$(basename $file)
	gdalwarp -tr 0.01 0.01 -te -96.0 29.8 -94.5 30.8 $file /home/ZhiLi/CRESTHH/data/evap/${filename}.tif

done
