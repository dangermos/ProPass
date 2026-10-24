// The shape of web/public/results.json, written by scripts/publish_results.py from the benchmark reports.
export type Split={runs:number;seeds:number[];passed:number;auto:number;held:number;extra:number;extra_incomplete:number;extra_short?:number;extra_over?:number;by_design?:number;wrong:number;missed:number;false_adds:number;barcode:number;charged:number;scenes:Record<string,number>;top_reasons:[string,number][]};

// What the precautionary hand-offs held, worded like the README (scripts/publish_results.py precaution()).
export function precaution(t:Split){
  const right=t.extra-t.extra_incomplete,short=t.extra_short??0,over=t.extra_over??0;
  const parts=[short?`${short} ${short===1?'was':'were'} missing items (${t.missed} in all), so closing ${short===1?'it':'them'} would have undercharged`:'',
    over?`${over} had ${t.false_adds===1?'one item':`${t.false_adds} items`} too many, so closing ${over===1?'it':'them'} would have overcharged`:''].filter(Boolean);
  return `${right} of those ${t.extra} were already right.`+(parts.length?` Of the other ${t.extra_incomplete}, ${parts.join('; ')}.`:'')+' Because they went to a person, none of them closed with a wrong charge.';
}
