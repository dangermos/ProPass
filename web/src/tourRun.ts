import type { Cue } from './sound';

// A recorded run and what the trained models decided, built by scripts/build_tour.py.
export type Line={sku:string;name:string;quantity:number;rating?:string|null;source?:string|null};
export type Run={scenario:string;seed:number;description:string;duration:number;expected:Line[];exact_cart:boolean;
  review_required:boolean;expected_review:boolean;passed:boolean;steps:{t:number;lines:Line[]}[];notes:{t:number;text:string;kind?:Cue}[]};
export type Outcome={tone:'pass'|'assist'|'fail';title:string;text:string};

// The cart as it stood at video time t; once the video has ended, the final cart.
export function cartAt(run:Run|null,time:number,ended:boolean):Line[]{
  const step=run?.steps.filter(s=>s.t<=time).pop();
  return ended&&run?run.steps[run.steps.length-1]?.lines??[]:step?.lines??[];
}

export function outcomeOf(run:Run|null):Outcome|null{
  return !run?null:run.passed?{tone:'pass',title:run.expected_review?'Correctly held for an associate':'Closed automatically, exactly right',
      text:run.expected_review?'This scene is meant to need a person, and the system asked for one.':'Every item was counted once and identified. No one had to step in.'}
    :run.review_required?{tone:'assist',title:'Handed to an associate',text:run.exact_cart?'The cart was right, but the system was not sure enough to close it on its own.':'The system could not settle every item, so it kept what it had and asked for help instead of guessing.'}
    :{tone:'fail',title:'Closed with a wrong cart',text:'This run is a miss: the cart was closed without the right items.'};
}

// How a run ends, as the project page's scene grid labels it.
export const endingOf=(run:Pick<Run,'passed'|'expected_review'|'review_required'>)=>run.passed?(run.expected_review?'held':'pass'):run.review_required?'assist':'fail';
