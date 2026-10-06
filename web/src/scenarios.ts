// Must match ProPassScenarios in unity/Assets/ProPass/Runtime/ProPassScenario.cs and SCENARIOS in api/store.py.
export type ScenarioInfo = {id:string;name:string;detail:string;tests:string;group:'classic'|'messy'};

export const scenarios:ScenarioInfo[] = [
  {id:'single',name:'Single item',detail:'One drill kit, one clean crossing',tests:'Counting once',group:'classic'},
  {id:'duplicate',name:'Identical products',detail:'Same SKU, two physical units',tests:'Physical identity',group:'classic'},
  {id:'mixed',name:'Mixed cart',detail:'Three different products in one trip',tests:'SKU recognition',group:'classic'},
  {id:'occlusion',name:'Temporary occlusion',detail:'A hand hides the box for 0.6 s',tests:'Re-attachment',group:'classic'},
  {id:'remove',name:'Change of mind',detail:'Carried in, then carried back out',tests:'Reverse removal',group:'classic'},
  {id:'unknown',name:'Unknown product',detail:'An unenrolled gray package',tests:'Rejection + review',group:'classic'},
  {id:'hands',name:'Busy hands',detail:'Hands keep covering the products',tests:'Partial occlusion',group:'messy'},
  {id:'shopper',name:'Crossing shopper',detail:'Someone walks through the view',tests:'Occlusion by people',group:'messy'},
  {id:'flatbed',name:'Lumber flatbed',detail:'Seconds of full occlusion',tests:'Long occlusion',group:'messy'},
  {id:'edge',name:'Edge of frame',detail:'Enters from below, hugs the rail',tests:'Partial views',group:'messy'},
  {id:'stacked',name:'Stacked boxes',detail:'One package carried on another',tests:'Touching objects',group:'messy'},
  {id:'distractors',name:'Distractors',detail:'A phone, cup and bag come along',tests:'False positives',group:'messy'},
  {id:'bystander',name:'Next-aisle shopper',detail:'Carries a product past the lane',tests:'Lane awareness',group:'messy'},
  {id:'hesitate',name:'Hesitation',detail:'Pause, step back, then decide',tests:'Reversible events',group:'messy'},
  {id:'parked',name:'Parked flatbed',detail:'Hidden from the lane camera for 7–9 s',tests:'Second camera',group:'messy'},
  {id:'locked',name:'Locked-cage tool',detail:'A restricted item comes through',tests:'Associate release',group:'messy'},
  {id:'lumber',name:'Lumber',detail:'Boards with no barcode',tests:'Recognized by look',group:'messy'},
];

export const scenarioName = (id?:string) => scenarios.find(s => s.id === id)?.name ?? id ?? '—';
