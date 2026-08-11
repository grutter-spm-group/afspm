#include ":AsylumResearch:Code3D:MainPanel"  // For ScanParmsInit, FmapSetVarFunc
#include ":AsylumResearch:Code3D:Controls"  // For BuildSetVarStructByParmName
#include ":AsylumResearch:Code3D:PanelFuncs"  // For GhostDelayUpdate

// NOTE: non-returning methods should return 0 on success, 1 on failure.

#ifdef ARrtGlobals
#pragma rtGlobals=1     // Use modern global access method
#else
#pragma rtGlobals=3     // Use strict wave reference mode
#endif

// Copied from MainPanel to not have to change anything...
Static Function ScanParmsInit(this,[ScanPoints,ScanRate,ScanSize,SlowRatio,IsIMS])
	Struct ScanParms &this
	Variable ScanPoints, ScanRate, ScanSize, SlowRatio, IsIMS
	
	Wave/Z MVW = root:Packages:MFP3D:Main:Variables:MasterVariablesWave
	if (ParamIsDefault(ScanPoints))
		ScanPoints = SafeGVByLabel(MVW,"ScanPoints")
	endif
	if (ParamIsDefault(ScanRate))
		ScanRate = SafeGVByLabel(MVW,"ScanRate")
	endif
	if (ParamIsDefault(ScanSize))
		ScanSize = SafeGVByLabel(MVW,"ScanSize")
	endif
	if (ParamIsDefault(SlowRatio))
		SlowRatio = SafeGVByLabel(MVW,"SlowRatio")
	endif
	if (ParamIsDefault(IsIMS))
		this.IsIMS = IsImageFormatIMS(ScanRate=ScanRate,ScanPoints=ScanPoints)
	else
		this.IsIMS = IsIMS
	endif
	
	this.MasterSampleRate = GetMasterSampleRate(IsIMS=This.IsIMS)
	this.ScanPoints = ScanPoints
	this.ScanRate = ScanRate
	this.FastScanSize = ScanSize/SlowRatio
	
	if (this.IsIMS)
		this.ScanRate = CalcScanRate(This.ScanRate)
		this.SampleRate = This.ScanPoints*This.ScanRate*2.5
		if (this.SampleRate > this.MasterSampleRate)
			this.ScanPoints = floor(this.MasterSampleRate/this.ScanRate/2.5)
			this.ScanPoints -= mod(this.ScanPoints,8)
		endif
	else
		this.SampleRate = this.ScanPoints*this.ScanRate*2.5
		this.Decimation = ARGetDeci(this.SampleRate,MasterRate=this.MasterSampleRate)
		this.SampleRate = this.MasterSampleRate/this.Decimation
	
		this.ScanRate = this.MasterSampleRate/(this.Decimation*this.ScanPoints*2.5)
		if ((this.ScanRate > MVW[%ScanRate][%High]))
			this.Decimation += 1
			this.SampleRate = this.MasterSampleRate/this.Decimation
			this.ScanRate = this.SampleRate/this.ScanPoints/2.5
		endif
	endif
	Variable ScanLineTime = 1/this.ScanRate
	ScanLineTime /= 2.5		//the time during a linear region of the image
	this.ScanSpeed = This.FastScanSize/ScanLineTime
	
End //ScanParmsInit

// This is a copy-paste from FMapSetVarFunc(), trying to replicate it's functionality so we may set the scan rate safely.
Function SetScanRate(VarNum)
	Variable VarNum
	
	// Variables declared later on...weird
	Variable scanStatus = GV("ScanStatus")
	Variable delay_Update = GV("DelayUpdate")		//underscore to avoid conflict Igor built in Operation.
	String RebuildList = ""
	
	Variable OldScanRate = Nan, OldIMS, OldScanShape, OldMarker
	Variable OldScanSpeed, OldScanPoints
	Struct ScanParms ScanParms
	
	OldScanRate = GVLV("ScanRate")
	OldIMS = IsImageFormatIMS(ScanRate=OldScanRate)
	OldScanShape = IsScanShapeSine(ScanRate=OldScanRate,IMSMode=OldIMS)
	OldMarker = ImagesNeedMarkers(ScanRate=OldScanRate)
	ScanParmsInit(ScanParms,ScanRate=VarNum)
	//OldScanSpeed = GV("ScanSpeed")
	//OldScanPoints = GV("ScanPoints")
	
	VarNum = ScanParms.ScanRate

	PV("ScanSpeed",ScanParms.ScanSpeed)	//calculate the new ScanSpeed. Added SlowRatio as that reduces the scan size in the fast direction
	newUpdateClickVar("ScanSpeed",ScanParms.ScanSpeed)

	//PV("ScanSpeed",OldScanSpeed)	//calculate the new ScanSpeed. Added SlowRatio as that reduces the scan size in the fast direction
	//newUpdateClickVar("ScanSpeed",OldScanSpeed)
	if (scanStatus)// && delay_Update)
		GhostDelayUpdate()
		PV("DelayUpdate",delay_Update | cScanDelayUpdate)
		ARStatus(Nan,"",StatusLine=cARHDStatusLine)
		PV("ImageFrameTime",0)
	endif
	PV("ScanRate",VarNum)	//update this so that CalcSampleRate will work correctly
	if (ScanParms.ScanPoints != GV("ScanPoints"))
		CallSetVarSimple(FMapSetVarFunc,"ScanPoints",TabStr="_0",Value=ScanParms.ScanPoints)
	endif
	CalcSampleRate()	//this updates the sample rate displayed on the Filter Panel
	if (VarNum > cScanAngleNeedsValidationRate)
		Struct WMSetvariableAction ScanAngleSetVar
		BuildSetVarStructByParmName(ScanAngleSetVar,"ScanAngle","_0",Value=GV("ScanAngle"))
		ScanAngleSetVar.EventCode = 2		//the scanAngle needs to do special things with a click, so we can't lie here.
		FmapSetVarFunc(ScanAngleSetVar)

		//CallSetVarSimple(FMapSetVarFunc,"ScanAngle",TabStr="_0",Value=GV("ScanAngle"))
	else
		//this is to force the new PVH("ScanSize", to happen
		ScanAngleFunc(GV("ScanAngle"))
	endif

	GhostSectionPanel()		//enable / Disable Section Controls
	CalcScanTime()
	if (!ScanStatus)
		UpdateOnIMSFormatChange(OldIMS,RebuildList)
		UpdateOnScanShapeChange(OldScanShape)
		UpdateOnImageMarkerChange(OldMarker)
	endif
	NewRebuildPanels(RebuildList)
	
	return(0)
End Function