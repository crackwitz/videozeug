movmark: takes trecmarkers output and patches it into the XMP_ box of a .mov file

the .mov file has to have:
* moov.udta.XMP_ box
* ... at the end of the file
* "Chapters" track in the XMP data

add a *chapter* marker to the mov file within Premiere to make this happen.
