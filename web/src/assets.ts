// Static files in web/public. BASE_URL is '/' locally and the repository path on GitHub Pages.
export const asset=(path:string)=>`${import.meta.env.BASE_URL}${path.replace(/^\//,'')}`;
