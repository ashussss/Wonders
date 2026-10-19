/**
 * Autofill helper for link-building submissions.
 *
 * The admin copies an approved draft ("Copy for autofill") and clicks the
 * "ShowUp Fill" bookmark on the target site's form. The bookmarklet reads the
 * clipboard, fills matching empty fields and outlines them in orange.
 *
 * It NEVER clicks submit, never signs up and never touches password, file or
 * hidden fields. The person checks the form and presses Submit themselves.
 */

const SITE = "https://showupai.live";

export function buildFillPayload(item) {
  const d = item?.draft || {};
  const list = (v) => (Array.isArray(v) ? v.map((x) => (typeof x === "string" ? x : x?.title || "")).filter(Boolean) : []);
  const fields = {
    name: "ShowUpAI",
    website: SITE,
    tagline: d.tagline || d.one_liner || d.title || "",
    short_description: d.short_description || d.subtitle || d.description || "",
    description: d.long_description || d.description || d.about || d.body_markdown || d.answer || "",
    features: list(d.key_features).join("\n"),
    categories: list(d.categories || d.topics).join(", "),
    pricing: d.pricing_note || "$29, $79 and $199 per month, 14-day free trial",
    comment: d.maker_comment || d.first_post || "",
  };
  return JSON.stringify({ showup_fill: 1, site: item?.domain || "", fields });
}

// Runs on the third-party page. Plain ES5-ish so it works anywhere.
const SOURCE = `(function(){
var RULES=[
 ["website",/(web ?site|homepage|url|link|domain)/i],
 ["tagline",/(tagline|slogan|headline|one.?liner|catch ?phrase)/i],
 ["short_description",/(short desc|summary|subtitle|elevator|brief|excerpt)/i],
 ["features",/(feature)/i],
 ["categories",/(categor|tags?\\b|topics?)/i],
 ["pricing",/(pric)/i],
 ["comment",/(maker comment|first comment|founder)/i],
 ["description",/(desc|about|details|overview|tell us|body)/i],
 ["name",/(product|company|app|tool|startup|software|brand)?\\s*name/i]
];
var SKIP=/(first ?name|last ?name|full ?name|your ?name|user ?name|e-?mail|password|phone|search)/i;
function labelOf(el){
 var t=[el.getAttribute("aria-label"),el.placeholder,el.name,el.id];
 if(el.id){var l=document.querySelector('label[for="'+el.id+'"]');if(l)t.push(l.innerText||l.textContent);}
 var p=el.closest("label");if(p)t.push(p.innerText||p.textContent);
 var prev=el.parentElement&&el.parentElement.previousElementSibling,pt=prev&&(prev.innerText||prev.textContent);if(pt&&pt.length<80)t.push(pt);
 return t.filter(Boolean).join(" ");
}
function setVal(el,v){
 var proto=el.tagName==="TEXTAREA"?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;
 var d=Object.getOwnPropertyDescriptor(proto,"value");d&&d.set?d.set.call(el,v):(el.value=v);
 el.dispatchEvent(new Event("input",{bubbles:true}));el.dispatchEvent(new Event("change",{bubbles:true}));
 el.style.outline="2px solid #EA580C";
}
function note(msg){
 var n=document.createElement("div");n.textContent=msg;
 n.style.cssText="position:fixed;z-index:2147483647;right:16px;bottom:16px;max-width:320px;padding:12px 14px;background:#111;color:#fff;font:14px/1.4 system-ui;border-left:4px solid #EA580C;border-radius:8px";
 document.body.appendChild(n);setTimeout(function(){n.remove();},9000);
}
function fill(raw){
 var data;try{data=JSON.parse(raw);}catch(e){return note("ShowUp Fill: copy a draft from /app/links first.");}
 if(!data||!data.showup_fill)return note("ShowUp Fill: copy a draft from /app/links first.");
 var f=data.fields,used={},n=0;
 var els=document.querySelectorAll("input[type=text],input[type=url],input:not([type]),textarea");
 for(var i=0;i<els.length;i++){
  var el=els[i];if(el.value||el.disabled||el.readOnly||el.offsetParent===null)continue;
  var lab=labelOf(el);if(!lab||SKIP.test(lab))continue;
  for(var r=0;r<RULES.length;r++){
   var k=RULES[r][0];if(used[k]||!f[k])continue;
   if(k==="website"&&el.type!=="url"&&!/(web ?site|homepage|url)/i.test(lab))continue;
   if(RULES[r][1].test(lab)){setVal(el,f[k]);used[k]=1;n++;break;}
  }
 }
 note(n?"ShowUp Fill: "+n+" field(s) filled (orange). Check them, then press Submit yourself.":"ShowUp Fill: no matching empty fields on this page. Paste manually.");
}
if(navigator.clipboard&&navigator.clipboard.readText){
 navigator.clipboard.readText().then(fill,function(){fill(window.prompt("Paste the ShowUp autofill text")||"");});
}else{fill(window.prompt("Paste the ShowUp autofill text")||"");}
})();`;

export const BOOKMARKLET = `javascript:${encodeURIComponent(SOURCE.replace(/\n\s*/g, ""))}`;
