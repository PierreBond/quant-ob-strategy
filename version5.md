//@version=5
indicator(title="Order Blocks", overlay=true,max_bars_back=5000, format = format.volume)

// Input options
inputRange = input.int(25, "Candle Range", minval=5, maxval=100, step=1, group = "BASIC SETTINGS")
bullishBreakerSource = input.source(close, title="Bullish Breaker Source")
bearishBreakerSource = input.source(close, title="Bearish Breaker Source")

// optional displays
showPD = input.bool(false, "Show Previous Day High/Low", group = "Extras")
showBearishBOS = input.bool(false, "Show Bearsish BOS Line", group = "Extras")
showBullishBOS = input.bool(false, "Show Bullish BOS Line", group = "Extras")
showBreakerCandles = input.bool(false, "Highlight Breaker Candles", group = "Extras")
showRetestCandles = input.bool(false, "Highlight Re-test Candles", group = "Extras")
showTrendColours = input.bool(false, "Show Trend Colours", group = "Extras")
showAlerts = input.bool(false, "Trigger Alerts", group = "Extras")
useMitigatedBlocks = input.bool(false, "Show Mitigated Blocks", group = "Extras")

// colours & styles
bearishOBColour = input.color(color.rgb(219,166,50, 80), title = "Bearish Order Block Colour", group = "STYLES")
bullishOBColour = input.color(color.rgb(192,230,174, 60), title= "Bullish Order Block Colour", group = "STYLES")
mitigatedOBColour = input.color(color.rgb(207,203,202, 80), title= "Mitigated Order Block Colour", group = "STYLES")
BOSCandleColour = input.color(color.yellow, title= "Breaker Candle Colour", group = "STYLES")
shortRetestCandleColour = input.color(color.purple, title= "Short Re-Test Candle Colour", group = "STYLES")
longRetestCandleColour = input.color(color.orange, title= "Long Re-Test Candle Colour", group = "STYLES")
bullishTrendColor = input.color(color.lime, title= "Bullish Trend Colour", group = "STYLES")
bearishTrendColour = input.color(color.red, title= "Bearish Trend Colour", group = "STYLES")


// candle colouring
var int CandleColourMode = 0
var bool BosCandle = false
var bool bullishAlert = false
var bool bearishAlert = false
var bool shortRetestCandle = false
var bool longRetestCandle = false

// tracking for entries
var int lastDownIndex=0
var float lastDown=0
var float lastLow=0

var int lastUpIndex=0
var float lastUp=0
var float lastUpLow=0
var float lastUpOpen=0
var float lastHigh=0
var float lastBullBreakLow=0

// structure
var int structureLowIndex=0
float structureLow=1000000

// order block drawing arrays
var longBoxes = array.new_box()
var longBoxStart = array.new_int()
var longBoxState = array.new_int()
var shortBoxes = array.new_box()
var shortBoxStart = array.new_int()
var shortBoxState = array.new_int()
var bosLines = array.new_line()

var int lastLongIndex=0
var int lastShortIndex=0
BosCandle:=false
bullishAlert:=false
bearishAlert:=false
shortRetestCandle:=false
longRetestCandle:=false

PDH = request.security(syminfo.tickerid,"D",high[1])
PDL = request.security(syminfo.tickerid,"D",low[1])

if(showPD)
    var line l_pdh = na, var line l_pdo = na, var line l_pdl = na, var label lbl_pdh = na, var label lbl_pdl = na
    if barstate.islast
        lbl_pdh := label.new(bar_index + 8, PDH, "PDH", style=label.style_label_left, textcolor = color.white)
        lbl_pdl := label.new(bar_index + 8, PDL, "PDL", style=label.style_label_left, textcolor = color.white)
        l_pdh := line.new(bar_index-1, PDH, bar_index + 8, PDH, extend=extend.left, color=color.blue)
        l_pdl := line.new(bar_index-1, PDL, bar_index+8, PDL, extend=extend.left, color=color.blue)
    line.delete(l_pdh[1])
    line.delete(l_pdo[1])
    line.delete(l_pdl[1])
    label.delete(lbl_pdh[1])
    label.delete(lbl_pdl[1])

// functions
structureLowIndexPointer(len) =>
    float minValue = ta.highest(high, inputRange)[1]
    int minIndex = bar_index 
    for i = 1 to len
        if low[i] < minValue
            minValue := low[i]
            minIndex := bar_index[i]
    minIndex

withinBullishBlock(position) =>
    bool result = false
    if((array.size(longBoxes)>0))
        for i = (array.size(longBoxes)-1) to 0
            box=array.get(longBoxes,i)
            top=box.get_top(box)
            bottom=box.get_bottom(box)
            if(position<top and position>bottom)
                result:=true
    result


// get the lowest point in the range
structureLow:=ta.lowest(low, inputRange)[1]
structureLowIndex:=structureLowIndexPointer(inputRange)


// bearish break of structure
if(ta.crossunder(bearishBreakerSource,structureLow))
    if((bar_index - lastUpIndex) < 1000)
        // add bear order block
        array.push(shortBoxStart, bar_index)
        array.push(shortBoxState, 0)
        array.push(shortBoxes,box.new(left=lastUpIndex, top=lastHigh, bottom=lastUpLow,right=lastUpIndex, bgcolor=bearishOBColour,border_color=color.rgb(207,203,202, 100), extend=extend.right))
        // add bearish bos line
        if(showBearishBOS)
            array.push(bosLines, line.new(structureLowIndex, structureLow, bar_index, structureLow, color= color.red, style=line.style_solid, width = 2))
        // show bos candle
        BosCandle:=true
        // color mode bear
        CandleColourMode:=0
        lastShortIndex:=lastUpIndex
        bearishAlert:=true

// bullish break of structure?
if((array.size(shortBoxes)>0))
    for i = (array.size(shortBoxes)-1) to 0
        sbox=array.get(shortBoxes,i)  
        lstart=array.get(shortBoxStart, i)  
        lstate=array.get(shortBoxState, i)
        top=box.get_top(sbox)
        left=box.get_left(sbox)
        bottom=box.get_bottom(sbox)
        if(high>bottom and low < bottom and bar_index>lstart and lstate==0 and useMitigatedBlocks)
            sbox.set_bgcolor(mitigatedOBColour)
            shortRetestCandle:=true
            array.set(shortBoxState, i, 1)
        if(bullishBreakerSource>top)
            // remove the short box 
            box.delete(sbox)
            array.remove(shortBoxState, i)
            array.remove(shortBoxes, i)
            array.remove(shortBoxStart, i)
            bullishAlert:=true
            // ok to draw?
            if((bar_index - lastDownIndex) < 1000 and bar_index>lastLongIndex) 
                // add bullish order block
                array.push(longBoxStart, bar_index+1)
                array.push(longBoxState, 0)
                array.push(longBoxes, box.new(left=lastDownIndex, top=lastDown, bottom=lastLow,right=lastDownIndex, bgcolor=bullishOBColour,border_color=color.rgb(207,203,202, 100), extend=extend.right))
                // add bullish bos line
                if(showBullishBOS)
                    array.push(bosLines, line.new(left, top, bar_index, top, color= color.green, style=line.style_solid, width = 1))
                // show bos candle
                BosCandle:=true
                // colour mode bullish
                CandleColourMode:=1
                // record last bull bar index to prevent duplication
                lastLongIndex:=bar_index
                lastBullBreakLow:=low

// alerts
alertcondition(bullishAlert and showAlerts, "Bullish break of structure", 'bullish break of structure was triggered')
alertcondition(bearishAlert and showAlerts, "Bearish break of structure", 'bearish break of structure was triggered')
alertcondition(shortRetestCandle and showAlerts, "Bearish order block re-tested", 'bearish order block has been re-tested')
alertcondition(longRetestCandle and showAlerts, "Bullish order block re-tested", 'bullish order block has been re-tested')

// update bullish order blocks
if((array.size(longBoxes) > 0))
    for i = (array.size(longBoxes)-1) to 0
        lbox=array.get(longBoxes,i)
        lstart=array.get(longBoxStart, i)
        lstate=array.get(longBoxState, i)
        bottom=box.get_bottom(lbox)
        top=box.get_top(lbox)
        boxLeft=box.get_left(lbox)
        if(low<=top and high>top and bar_index>lstart and lstate==0)
            if(useMitigatedBlocks)
                lbox.set_bgcolor(mitigatedOBColour)
            longRetestCandle:=true
            array.set(longBoxState, i, 1)
        if(close<bottom)
            array.remove(longBoxStart, i)
            array.remove(longBoxState, i)
            array.remove(longBoxes, i)
            box.delete(lbox)


// candle colouring
CandleColour= CandleColourMode==1?bullishTrendColor:bearishTrendColour
CandleColour:= BosCandle and showBreakerCandles?BOSCandleColour:CandleColour
CandleColour:=shortRetestCandle and showRetestCandles?shortRetestCandleColour:CandleColour
CandleColour:=longRetestCandle and showRetestCandles?longRetestCandleColour:CandleColour
barcolor(showTrendColours?CandleColour:na)
barcolor(showBreakerCandles and BosCandle?CandleColour:na)

// record last up and down candles
if(close<open)
    lastDown:=high
    lastDownIndex:=bar_index
    lastLow:=low

if(close>open)
    lastUp:=close
    lastUpIndex:=bar_index
    lastUpOpen:=open
    lastUpLow:=low
    lastHigh:=high
    
// update last high/low for more accurate order block placements
lastHigh:=high>lastHigh?high:lastHigh
lastLow:=low<lastLow?low:lastLow
