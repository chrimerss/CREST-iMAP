for file in pet/*.asc
do
	filename=$(basename $file)
	gdalwarp -tr 0.01 0.01 -te -95.83 29.79 -95.05 30.18 $file /home/ZhiLi/CRESTHH/data/evap/${filename}.tif

done
