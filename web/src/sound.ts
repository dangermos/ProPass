// Sound for the recorded tour, made in the browser with Web Audio: no audio files.
// A quiet store-lane bed plays while a run plays, and each decision the system makes has a cue:
// a scanner beep for a barcode read, a chime when an item enters the cart, a falling tone when
// one is taken back out, and a two-note call when an associate is needed.
export type Cue='scan'|'add'|'remove'|'assist'|'identify'|'pass'|'handoff';

let context:AudioContext|null=null,master:GainNode|null=null,bed:GainNode|null=null,wheels:GainNode|null=null;

function noise(ctx:AudioContext,seconds:number,brown:boolean){
  const buffer=ctx.createBuffer(1,ctx.sampleRate*seconds,ctx.sampleRate),data=buffer.getChannelData(0);
  let last=0;
  for(let i=0;i<data.length;i++){const white=Math.random()*2-1;last=brown?(last+0.02*white)/1.02:white;data[i]=brown?last*3.5:white;}
  const source=ctx.createBufferSource();source.buffer=buffer;source.loop=true;return source;
}

/** Must be called from a click: browsers only start audio after a user gesture. */
export function soundOn(){
  if(!context){
    context=new AudioContext();master=context.createGain();master.gain.value=.9;master.connect(context.destination);
    // Room tone: low rumble of a big store plus a faint air-handling hiss.
    bed=context.createGain();bed.gain.value=0;bed.connect(master);
    const rumble=noise(context,4,true),low=context.createBiquadFilter();low.type='lowpass';low.frequency.value=220;
    const rumbleGain=context.createGain();rumbleGain.gain.value=.5;rumble.connect(low).connect(rumbleGain).connect(bed);rumble.start();
    const hiss=noise(context,3,false),band=context.createBiquadFilter();band.type='bandpass';band.frequency.value=3200;band.Q.value=.4;
    const hissGain=context.createGain();hissGain.gain.value=.012;hiss.connect(band).connect(hissGain).connect(bed);hiss.start();
    // Cart wheels: band-passed noise with a slow wobble, heard only while the run is moving.
    wheels=context.createGain();wheels.gain.value=0;wheels.connect(master);
    const roll=noise(context,2,true),rollBand=context.createBiquadFilter();rollBand.type='bandpass';rollBand.frequency.value=480;rollBand.Q.value=1.2;
    const wobble=context.createOscillator(),depth=context.createGain();wobble.frequency.value=5.5;depth.gain.value=140;wobble.connect(depth).connect(rollBand.frequency);wobble.start();
    roll.connect(rollBand).connect(wheels);roll.start();
  }
  void context.resume();
}

export function soundOff(){if(context)void context.suspend();}

/** Fade the lane bed and the wheels in or out as the video plays or pauses. */
export function moving(on:boolean){
  if(!context||!bed||!wheels)return;
  const now=context.currentTime;
  bed.gain.setTargetAtTime(on?.16:.05,now,.25);wheels.gain.setTargetAtTime(on?.07:0,now,.2);
}

function tone(frequency:number,start:number,length:number,volume:number,type:OscillatorType='sine'){
  if(!context||!master)return;
  const osc=context.createOscillator(),gain=context.createGain(),at=context.currentTime+start;
  osc.type=type;osc.frequency.value=frequency;
  gain.gain.setValueAtTime(0,at);gain.gain.linearRampToValueAtTime(volume,at+.008);gain.gain.exponentialRampToValueAtTime(.0005,at+length);
  osc.connect(gain).connect(master);osc.start(at);osc.stop(at+length+.02);
}

export function cue(kind:Cue){
  if(!context||context.state!=='running')return;
  if(kind==='scan')tone(2350,0,.09,.22,'square');
  else if(kind==='add'){tone(880,0,.22,.2);tone(1318.5,.09,.32,.2);}
  else if(kind==='remove'){tone(660,0,.16,.18);tone(440,.11,.26,.18);}
  else if(kind==='assist'){tone(587.3,0,.28,.2,'triangle');tone(466.2,.26,.42,.2,'triangle');}
  else if(kind==='identify')tone(1500,0,.04,.05);
  else if(kind==='pass'){tone(659.3,0,.2,.18);tone(784,.12,.2,.18);tone(1046.5,.24,.5,.2);}
  else if(kind==='handoff'){tone(523.3,0,.3,.18,'triangle');tone(523.3,.36,.5,.18,'triangle');}
}
