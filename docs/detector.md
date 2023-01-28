## Short outlook

## JSON headers
This is the format for 6.1.2 (example with Moench):
```json
{
    "jsonversion": 4,
    "bitmode": 16,
    "fileIndex": 0,
    "detshape": [
        1,
        1
    ],
    "shape": [
        400,
        400
    ],
    "size": 320000,
    "acqIndex": 4,
    "frameIndex": 0,
    "progress": 100.0,
    "fname": "//run",
    "data": 1,
    "completeImage": 1,
    "frameNumber": 4,
    "expLength": 0,
    "packetNumber": 239,
    "bunchId": 0,
    "timestamp": 0,
    "modId": 0,
    "row": 0,
    "column": 0,
    "reserved": 0,
    "debug": 0,
    "roundRNumber": 0,
    "detType": 5,
    "version": 1,
    "flipRows": 0,
    "quad": 0,
    "addJsonHeader": {
        "emin": "500"
    }
}
```

Changes from  6.x.x to 7.0.0:
4 field names have changed from 6.x.x to 7.x.x because they have also been changed in the detector udp header. 
Since the meaning has not changed, the udp header version stays the same as well as the  zmq header version.
detSpec1 <- bunchId
detSpec2 <- reserved
detSpec3 <- debug
detSpec4 <- roundRNumber

In case, you were wondering about the type:
```json
{
    "jsonversion": unsigned int,
    "bitmode": unsigned int,
    "fileIndex": unsigned long int,
    "detshape": [
        unsigned int,
        unsigned int
    ],
    "shape": [
        unsigned int,
        unsigned int
    ],
    "size": unsigned int,
    "acqIndex": unsigned long int,
    "frameIndex": unsigned long int,
    "progress": double,
    "fname": string,
    "data": unsigned int,
    "completeImage": unsigned int,

    "frameNumber": unsigned long long int,
    "expLength": unsigned int,
    "packetNumber": unsigned int,
    "detSpec1": unsigned long int,
    "timestamp": unsigned long int,
    "modId": unsigned int,
    "row": unsigned int,
    "column": unsigned int,
    "detSpec2": unsigned int,
    "detSpec3": unsigned int,
    "detSpec4": unsigned int,
    "detType": unsigned int,
    "version": unsigned int,

    "flipRows": unsigned int,
    "quad": unsigned int,
    "addJsonHeader": {
        string : string
    }
}
```

| Field            | Description                                                                                              |
| ---------------- | -------------------------------------------------------------------------------------------------------- |
| jsonversion      | Version of the json header. Value at 4 for v6.x.x   and v7.x.x                                           |
| bitmode          | Bits per pixel [4\|8\|16\|32]                                                                            |
| fileIndex        | Current file acquisition index                                                                           |
| detshape         | Geometry of the entire detector                                                                          |
| shape            | Geometry of the current port streamed out                                                                |
| size             | Size of image of current port in bytesout                                                                |
| acqIndex         | Frame number from the detector (redundant)                                                               |
| frameIndex       | Frame number of current acquisition (Starting at 0)                                                      |
| progress         | Progress of current acquisition in %                                                                     |
| fname            | Current file name                                                                                        |
| data             | 1 if there is data following 0 if dummy header                                                           |
| completeImage    | 1 if no missing packets for this frame in this port,   else 0                                            |
| frameNumber      | Frame number [From detector udp header]                                                                  |
| expLength        | subframe number (32 bit eiger) or real time exposure   time in 100ns (others) [From detector udp header] |
| packetNumber     | Number of packets caught for that frame                                                                  |
| detSpec1         | See here [From detector udp header]                                                                      |
| timestamp        | Timestamp with 10 MHz clock [From detector udp   header]                                                 |
| modId            | Module Id [From detector udp header]                                                                     |
| row              | Row number in detector [From detector udp header]                                                        |
| column           | Column number in detector [From detector udp header]                                                     |
| detSpec2         | See here [From detector udp header]                                                                      |
| detSpec3         | See here [From detector udp header]                                                                      |
| detSpec4         | See here [From detector udp header]                                                                      |
| detType detSpec3 | Detector type enum See Detector enum [From   detector udp header]                                        |
| version          | Detector header version. At 2 [From detector udp   header]                                               |
| flipRows         | 1 if rows should be flipped. Usually for Eiger bottom.                                                   |
| quad             | 1 if its an Eiger quad.                                                                                  |
| addJsonHeader    | Optional custom parameters that is required for   processing code.                                       |

## Frame remapping
`moench03T1ReceiverDataNew.h` in `slsDetectorPackage` lines `66:110`
```cpp
int nadc = 32;
        int sc_width = 25;
        int sc_height = 200;

        int adc_nr[32] = {300, 325, 350, 375, 300, 325, 350, 375, 200, 225, 250,
                          275, 200, 225, 250, 275, 100, 125, 150, 175, 100, 125,
                          150, 175, 0,   25,  50,  75,  0,   25,  50,  75};

        int row, col;

        int isample;
        int iadc;
        int ix, iy;

        int npackets = 40;
        int i;
        int adc4(0);
	int off=sizeof(header);
        for (int ip = 0; ip < npackets; ip++) {
            for (int is = 0; is < 128; is++) {

                for (iadc = 0; iadc < nadc; iadc++) {
                    i = 128 * ip + is;
                    adc4 = (int)iadc / 4;
                    if (i < sc_width * sc_height) {
                        //  for (int i=0; i<sc_width*sc_height; i++) {
                        col = adc_nr[iadc] + (i % sc_width);
                        if (adc4 % 2 == 0) {
                            row = 199 - i / sc_width;
                        } else {
                            row = 200 + i / sc_width;
                        }
                        dataMap[row][col] = off +
                                            (nadc * i + iadc) * 2; //+16*(ip+1);
#ifdef HIGHZ
                        dataMask[row][col] = 0x3fff; // invert data
#endif
                        if (dataMap[row][col] < 0 ||
                            dataMap[row][col] >= off + nSamples * 2 * 32)
                            std::cout << "Error: pointer " << dataMap[row][col]
                                      << " out of range " << std::endl;
                    }
                }
            }
        }
```
will be pre-calculated and saved as numpy array of indexes with the following code:
```python
import numpy as np

# 32 numbers
nadc = 32
adc_nr = [300, 325, 350, 375, 300, 325, 350, 375,
    200, 225, 250, 275, 200, 225, 250, 275,
    100, 125, 150, 175, 100, 125, 150, 175,
    0, 25, 50, 75, 0, 25, 50, 75,
]
npackets = 40
sc_width = 25
sc_height = 200

ind = np.zeros([400, 400], dtype=np.int32)
for ip in range(npackets):
    for iss in range(128):
        for iadc in range(32):
            i = 128 * ip + iss
            adc4 = iadc // 4
            if i < sc_width * sc_height:
                col = adc_nr[iadc] + (i % sc_width)
                if adc4 % 2 == 0:
                    row = 199 - i // sc_width
                else:
                    row = 200 + i // sc_width
                ind[row, col] = 32 * i + iadc
np.save("reorder_pattern", ind)
```